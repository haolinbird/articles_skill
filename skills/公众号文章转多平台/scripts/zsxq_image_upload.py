"""Upload images to 知识星球 via qiniu, using upload_token obtained from MCP call_zsxq_api.

Usage:
  python zsxq_image_upload.py <token_file> <image1> [image2] ...

Steps:
  1. Get upload_token via MCP: call_zsxq_api POST /v2/uploads
     body: {"req_data": {"type": "image", "size": <file_bytes>, "name": "", "hash": ""}}
  2. Save token to a file (must be UTF-8 WITHOUT BOM), pass path as <token_file>
  3. Run this script to upload each image -> prints image_id per file
  4. Pass image_ids to create_topic as "image_ids": [..]
"""
import sys, os, json, uuid, urllib.request, urllib.error


def upload(upload_token, filepath):
    boundary = '----WebKitFormBoundary' + uuid.uuid4().hex
    CRLF = '\r\n'
    ext = os.path.splitext(filepath)[1].lstrip('.').lower()
    mime = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
            'gif': 'image/gif', 'webp': 'image/webp'}.get(ext, 'image/jpeg')
    basename = os.path.basename(filepath)
    with open(filepath, 'rb') as f:
        data = f.read()
    header = (f'--{boundary}{CRLF}Content-Disposition: form-data; name="file"; filename="{basename}"'
              f'{CRLF}Content-Type: {mime}{CRLF}{CRLF}').encode('utf-8')
    footer = (f'{CRLF}--{boundary}{CRLF}Content-Disposition: form-data; name="token"{CRLF}{CRLF}'
              f'{upload_token}{CRLF}--{boundary}--{CRLF}').encode('utf-8')
    body = header + data + footer

    req = urllib.request.Request('https://upload-z1.qiniup.com/', data=body, method='POST', headers={
        'accept': 'application/json',
        'referer': 'https://wx.zsxq.com/',
        'user-agent': 'Mozilla/5.0',
        'x-request-id': str(uuid.uuid4()),
        'x-version': '2.89.0',
        'content-type': f'multipart/form-data; boundary={boundary}',
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode('utf-8', errors='replace')
            return json.loads(text)
    except urllib.error.HTTPError as e:
        return {'_error': e.code, '_raw': e.read().decode('utf-8', errors='replace')}


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    token = open(sys.argv[1], encoding='utf-8-sig').read().strip()
    results = {}
    for p in sys.argv[2:]:
        r = upload(token, p)
        iid = (r.get('resp_data') or {}).get('image_id')
        results[p] = iid
        status = f'✓ {iid}' if iid else f'✗ {r}'
        print(f'{os.path.basename(p)}: {status}')
    print(json.dumps(results, ensure_ascii=False))
