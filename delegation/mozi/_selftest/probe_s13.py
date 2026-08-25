#!/usr/bin/env python3
"""擾動 SPEC 的盲測宣告，確認 S13 族每一條斷言都真的會叫。

S13 曾經因為 SPEC 改寫刪掉 parser 依賴的字面而靜默關閉，
0 NOTE 被誤讀成通過。這支就是那次事故的常設對策。
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
SPEC = ROOT / 'delegation' / 'mozi' / 'SPEC.md'
ACCEPT = ROOT / 'delegation' / 'mozi' / 'accept.py'

CASES = [
    ('對子數', '共 22 對', '共 23 對'),
    ('頂對子換人', '`兼愛中`[7]／`非命上`[8]＝0.683', '`尚同上`[3]／`尚同中`[7]＝0.683'),
    ('頂對子相似度', '`非命上`[8]＝0.683', '`非命上`[8]＝0.611'),
    ('章級帶寬', '相似度實測 0.023–0.276', '相似度實測 0.023–0.376'),
    ('段級對數', '另有 5 對超出 0.30', '另有 7 對超出 0.30'),
    ('段級最高值', '`非命下`[6]＝0.544', '`非命下`[6]＝0.644'),
]


def run():
    r = subprocess.run([sys.executable, str(ACCEPT), '--check-spec'],
                       cwd=str(ROOT), capture_output=True)
    return (r.stdout + r.stderr).decode('utf-8', 'replace')


def write_spec(text):
    # 一律走 bytes：read_text/write_text 在 Windows 會把 LF 換成 CRLF，
    # 本庫的 .gitattributes 強制 LF。
    SPEC.write_bytes(text.encode('utf-8'))


def main():
    orig = SPEC.read_bytes().decode('utf-8')
    bad = 0
    try:
        base = run()
        if '自檢 PASS' not in base:
            print('!! 基線就不乾淨，中止')
            print(base[-800:])
            return 1
        for name, old, new in CASES:
            if orig.count(old) != 1:
                print(f'!! {name}: 錨字串在 SPEC 出現 {orig.count(old)} 次，無法隔離')
                bad += 1
                continue
            write_spec(orig.replace(old, new))
            out = run()
            hits = [ln for ln in out.splitlines() if 'S13' in ln]
            if hits:
                print(f'OK   {name}: {hits[0].strip()}')
            else:
                print(f'FAIL {name}: 擾動後 S13 沒有反應（檢查可能是死的）')
                bad += 1
    finally:
        write_spec(orig)
    after = run()
    print('還原後：', after.strip().splitlines()[-1])
    if '自檢 PASS' not in after:
        bad += 1
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
