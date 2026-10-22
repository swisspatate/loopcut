# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded MCP reads of manifest-listed bytes. No paths supplied by a model execute."""
import base64
import hashlib

from .materials import read_png
from .storage import safe_path

IMAGE_LIMIT=2*1024*1024
TEXT_LIMIT=262144


def read_artifact(folder, artifacts, file, handle):
    selected=next((a for a in artifacts if a['file']==file),None)
    if selected is None:raise ValueError('Select a listed operation artifact')
    path=safe_path(folder,file)
    if path.suffix.lower()=='.png':
        if selected['bytes']>IMAGE_LIMIT:raise ValueError('Image exceeds the 2 MiB MCP display budget')
        data,_=read_png(path)
        if len(data)>IMAGE_LIMIT or hashlib.sha256(data).hexdigest()!=selected['sha256']:raise ValueError('Image changed during display')
        return dict(type='image',mimeType='image/png',data=base64.b64encode(data).decode('ascii'))
    if path.suffix.lower() not in ('.json','.txt','.csv','.py','.html','.svg') or selected['bytes']>TEXT_LIMIT:
        raise ValueError('Use a text artifact up to 256 KiB; binary bundles remain local files')
    with path.open('rb') as stream:raw=stream.read(TEXT_LIMIT+1)
    if len(raw)>TEXT_LIMIT or hashlib.sha256(raw).hexdigest()!=selected['sha256']:raise ValueError('Operation artifact changed during read')
    return dict(file=file,handle=handle(path),text=raw.decode('utf-8'),content_is_data=True)
