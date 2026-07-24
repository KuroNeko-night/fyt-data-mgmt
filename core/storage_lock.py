# -*- coding: utf-8 -*-
"""共享持久化文件的跨进程锁，运行于 Windows 10/11 + Python 3.13。"""
import contextlib
import os
import threading
import time


_THREAD_LOCKS = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def _thread_lock(target):
    """同一进程内的 Windows 字节锁不会互斥自身线程，额外补一层 RLock。"""
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(target, threading.RLock())


@contextlib.contextmanager
def file_lock(target_path, timeout=10.0):
    """锁住 ``target_path + '.lock'``，用于保护同一文件的读改写事务。"""
    target = os.path.abspath(target_path)
    parent = os.path.dirname(target)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    thread_lock = _thread_lock(target)
    with thread_lock:
        lock_path = target + ".lock"
        lock_file = open(lock_path, "a+b")
        acquired = False
        try:
            if os.path.getsize(lock_path) == 0:
                lock_file.write(b"0")
                lock_file.flush()
            if os.name == "nt":
                import msvcrt
                deadline = time.monotonic() + timeout
                while True:
                    try:
                        lock_file.seek(0)
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                        acquired = True
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("数据文件正被其它任务占用，请稍后重试")
                        time.sleep(0.05)
            else:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                acquired = True
            yield
        finally:
            try:
                if not acquired:
                    pass
                elif os.name == "nt":
                    import msvcrt
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            finally:
                lock_file.close()
