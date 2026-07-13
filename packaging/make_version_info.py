# -*- coding: utf-8 -*-
"""
生成 PyInstaller 用的 Windows 版本资源文件 version_info.txt
==========================================================
从 core/version.py 读取版本号，写出 exe 的“详细信息”属性。
一处改版本(version.py)，打包时自动同步到 exe 与安装包。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from core import version as V   # noqa: E402

_TMPL = u"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={vt},
    prodvers={vt},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(u'080404b0', [
        StringStruct(u'CompanyName', u'{pub}'),
        StringStruct(u'FileDescription', u'{name}'),
        StringStruct(u'FileVersion', u'{ver}'),
        StringStruct(u'InternalName', u'{appid}'),
        StringStruct(u'LegalCopyright', u'{copy}'),
        StringStruct(u'OriginalFilename', u'{appid}.exe'),
        StringStruct(u'ProductName', u'{name}'),
        StringStruct(u'ProductVersion', u'{ver}')])
    ]),
    VarFileInfo([VarStruct(u'Translation', [2052, 1200])])
  ]
)
"""


def build_text():
    vt = tuple(list(V.VERSION_TUPLE) + [0] * (4 - len(V.VERSION_TUPLE)))
    return _TMPL.format(vt=vt, ver=V.VERSION, name=V.APP_NAME, pub=V.PUBLISHER,
                        appid=V.APP_ID, copy=V.COPYRIGHT)


def write(path=None):
    path = path or os.path.join(HERE, "version_info.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_text())
    return path


if __name__ == "__main__":
    print("written:", write())
