# -*- coding: utf-8 -*-
"""共享持久化文件的跨进程锁，运行于 Windows 10/11 + Python 3.13。

锁文件位于 ``<目标文件>.lock``。Windows 使用 ``msvcrt.locking`` 字节锁，POSIX 使用
``fcntl.flock``；同一进程内再补一层线程 RLock，因为 Windows 字节锁不会互斥自身线程。
读改写 JSON 索引时必须通过 :func:`file_lock` 包住“读取 → 修改 → 写回”三段，配合临时
文件与原子替换才能保证多任务并发下不丢更新。
"""
import contextlib
import os
import threading
import time

# 进程内线程锁注册表：Windows 字节锁按文件句柄加锁，同一进程的两个线程不会互斥，
# 因此必须用线程锁先串行化；RLock 允许同一线程在嵌套事务中重复进入。
_THREAD_LOCKS = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def _thread_lock(target):
    """返回同一目标文件对应的进程内 RLock。

    所有读改写事务先取该线程锁，再取跨进程文件锁，顺序固定可避免死锁。
    """
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(target, threading.RLock())


def _ensure_lock_parent(target):
    """确保锁文件所在目录存在，便于在尚未建目录的输出路径上直接加锁。"""
    parent = os.path.dirname(target)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)


def _acquire_nt(lock_file, timeout):
    """Windows 非阻塞字节锁轮询，超时抛出带业务语义的 ``TimeoutError``。

    锁文件内容并不重要，仅需要一个稳定的 1 字节区域供 ``LK_NBLCK`` 锁定；先写入
    一个字节可避免某些文件系统对零长度文件加锁时返回空区域错误。
    """
    import msvcrt

    deadline = time.monotonic() + timeout
    while True:
        try:
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise TimeoutError("数据文件正被其它任务占用，请稍后重试")
            time.sleep(0.05)


def _acquire_posix(lock_file):
    """POSIX 使用阻塞式 ``flock``，等待时间由调用方控制超时策略。"""
    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)


def _release_nt(lock_file):
    """释放 Windows 字节锁；必须先定位到锁定区域才能解锁。"""
    import msvcrt

    lock_file.seek(0)
    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)


def _release_posix(lock_file):
    """释放 POSIX ``flock`` 独占锁。"""
    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def file_lock(target_path, timeout=10.0):
    """锁住 ``target_path + '.lock'``，用于保护同一文件的读改写事务。

    用法::

        with file_lock(index_path):
            data = _read_json(index_path)
            data["items"].append(new_item)
            _write_json_atomic(index_path, data)

    异常从 ``yield`` 处透传，锁总在 ``finally`` 中释放；``timeout`` 仅在 Windows
    轮询路径生效，POSIX 下 ``flock`` 为阻塞等待。
    """
    target = os.path.abspath(target_path)
    _ensure_lock_parent(target)

    with _thread_lock(target):
        lock_path = target + ".lock"
        lock_file = open(lock_path, "a+b")
        acquired = False
        try:
            # 先保证锁定区域非空，再按平台加锁。锁文件不承载业务数据，内容恒为 "0"。
            if os.path.getsize(lock_path) == 0:
                lock_file.write(b"0")
                lock_file.flush()
            if os.name == "nt":
                _acquire_nt(lock_file, timeout)
            else:
                _acquire_posix(lock_file)
            acquired = True
            yield
        finally:
            try:
                if acquired:
                    if os.name == "nt":
                        _release_nt(lock_file)
                    else:
                        _release_posix(lock_file)
            finally:
                lock_file.close()
