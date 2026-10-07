import hashlib, json, os, shutil, sys, tempfile, threading, zipfile
from pathlib import Path

BASE = '77c5583823409588ad5d24320d3d59d3a977f84013f4706c4d2408c79edc6038'
TARGET = '064bbb1737731e5877a469d1388a29c8b01b81de80ef82c20691739433d54911'
SIZE = 1214077377
HOME = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent

def digest(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(8*1024*1024), b''): h.update(b)
    return h.hexdigest()

def operate(folder, action, data=None, original=None, report=lambda s: None):
    import msvcrt
    root = Path(folder).resolve()
    dest = root / 'resources' / 'app.asar'
    backup = dest.with_name('app.asar.ko-original-beta5304')
    if not dest.is_file(): raise ValueError('게임 설치 폴더를 선택해 주세요. resources/app.asar가 없습니다.')
    lock = open(dest.with_name('ko-patch.lock'), 'a+b')
    temporary = None
    try:
        lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
        try: msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError: raise ValueError('다른 패치 작업이 진행 중입니다.')
        report('현재 파일 확인 중…')
        before = digest(dest)
        if before not in (BASE, TARGET): raise ValueError('지원하는 원본 또는 한글 패치가 아닙니다. 적용하지 않았습니다. 지원 버전: beta.5304')
        if action == 'apply' and before == TARGET: return '이미 이 한글 패치가 적용되어 있습니다.'
        if action == 'restore' and before == BASE: return '이미 원본 상태입니다.'
        if action not in ('apply', 'restore'): raise ValueError('잘못된 작업입니다.')
        source = dest if action == 'apply' else backup
        if action == 'restore' and not backup.exists() and original: source = Path(original).resolve()
        if not source.is_file() or digest(source) != BASE:
            raise ValueError('beta.5304 원본 백업이 없거나 일치하지 않습니다. 원본 파일 지정 후 다시 시도해 주세요.')
        if backup.exists() and digest(backup) != BASE: raise ValueError('기존 백업이 원본과 다릅니다. 백업을 덮어쓰지 않았습니다.')
        if shutil.disk_usage(dest.parent).free < SIZE*2 + 64*1024*1024:
            raise ValueError('백업과 임시 파일을 위해 여유 공간 2.5GB 이상이 필요합니다.')
        if not backup.exists():
            report('원본 백업 중…')
            fd, name = tempfile.mkstemp(prefix='ko-backup-', suffix='.tmp', dir=dest.parent); os.close(fd)
            temporary = Path(name)
            shutil.copyfile(source, temporary)
            if digest(temporary) != BASE: raise ValueError('백업 검증에 실패했습니다.')
            os.rename(temporary, backup); temporary = None
        fd, name = tempfile.mkstemp(prefix='ko-result-', suffix='.tmp', dir=dest.parent); os.close(fd)
        temporary = Path(name)
        report('한글 파일 생성 중…' if action == 'apply' else '원본 복원 준비 중…')
        if action == 'restore': shutil.copyfile(backup, temporary)
        else:
            with zipfile.ZipFile(data or HOME/'patch-data.zip') as z, open(backup, 'rb') as src, open(temporary, 'wb') as out:
                m = json.loads(z.read('manifest.json'))
                if (m['base_sha256'], m['target_sha256'], m['target_size']) != (BASE, TARGET, SIZE): raise ValueError('패치 데이터의 버전이 다릅니다.')
                total = 0
                for op in m['operations']:
                    if 'copy' in op:
                        offset, left = op['copy']
                        if offset < 0 or left < 0 or offset+left > os.fstat(src.fileno()).st_size: raise ValueError('잘못된 원본 범위입니다.')
                        src.seek(offset); stream = src
                    else:
                        stream = z.open(op['data']); left = z.getinfo(op['data']).file_size
                    try:
                        while left:
                            b = stream.read(min(left, 8*1024*1024))
                            if not b: raise ValueError('패치 데이터가 불완전합니다.')
                            total += len(b)
                            if total > SIZE: raise ValueError('패치 크기가 올바르지 않습니다.')
                            out.write(b); left -= len(b)
                    finally:
                        if stream is not src: stream.close()
                out.flush(); os.fsync(out.fileno())
        report('결과 검증 중…')
        expected = TARGET if action == 'apply' else BASE
        if digest(temporary) != expected: raise ValueError('결과 검증에 실패했습니다. 게임 파일은 변경하지 않았습니다.')
        if digest(dest) != before: raise ValueError('작업 중 게임 파일이 바뀌었습니다. 교체하지 않았습니다.')
        os.replace(temporary, dest); temporary = None
        return '한글 패치 적용 완료. 도구를 닫고 게임을 실행하세요.' if action == 'apply' else '원본 복원 완료. 백업은 보관됩니다.'
    finally:
        if temporary and temporary.exists(): temporary.unlink()
        lock.close()

def gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    import queue
    app = tk.Tk(); app.title('갈가두사 타워 한글 패치 · 설치 테스트용'); app.geometry('650x350'); app.resizable(False, False)
    frame = ttk.Frame(app, padding=20); frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Gargadusa’s Tower · Steam beta.5304', font=('맑은 고딕', 15)).pack(anchor='w')
    ttk.Label(frame, text='게임을 종료한 뒤 적용하세요. 일부 영어가 남아 있는 테스트 패치입니다.').pack(anchor='w', pady=12)
    folder = tk.StringVar(value=r'C:\Program Files (x86)\Steam\steamapps\common\GargadusasTower')
    ttk.Entry(frame, textvariable=folder, width=85).pack(fill='x')
    original = tk.StringVar(); state = tk.StringVar(value='게임 폴더를 확인하고 작업을 선택하세요.'); events = queue.Queue(); busy = [False]
    def browse():
        value = filedialog.askdirectory(title='게임 설치 폴더 선택')
        if value: folder.set(value)
    def choose():
        value = filedialog.askopenfilename(title='기존 beta.5304 원본 백업 선택')
        if value: original.set(value); state.set('복원 시 지정한 원본 백업을 검증합니다.')
    buttons = []
    def start(action):
        if not messagebox.askokcancel('게임 종료 확인', '게임과 Steam 업데이트를 종료했는지 확인해 주세요.\n선택한 게임 폴더의 파일을 변경합니다.'): return
        path, orig = folder.get(), original.get()
        busy[0] = True
        for b in buttons: b.configure(state='disabled')
        def run():
            try: events.put(('done', operate(path, action, original=orig or None, report=lambda s: events.put(('status', s)))))
            except Exception as e: events.put(('error', str(e)))
        threading.Thread(target=run, daemon=False).start()
    row = ttk.Frame(frame); row.pack(fill='x', pady=12)
    for label, command in [('폴더 선택', browse), ('한글 패치 적용', lambda: start('apply')), ('원본 복원', lambda: start('restore')), ('기존 원본 백업 지정', choose)]:
        b = ttk.Button(row, text=label, command=command); b.pack(side='left', padx=3); buttons.append(b)
    ttk.Label(frame, textvariable=state, wraplength=600).pack(anchor='w', pady=15)
    ttk.Label(frame, text='백업: resources/app.asar.ko-original-beta5304\n이미 한글 패치가 설치된 경우 중복 적용하지 않습니다.').pack(anchor='w')
    def poll():
        while not events.empty():
            kind, value = events.get(); state.set(value)
            if kind != 'status':
                busy[0] = False
                for b in buttons: b.configure(state='normal')
                (messagebox.showerror if kind == 'error' else messagebox.showinfo)('작업 결과', value)
        app.after(100, poll)
    def close():
        if busy[0]: messagebox.showinfo('작업 중', '파일 작업이 끝난 뒤 닫아 주세요.')
        else: app.destroy()
    app.protocol('WM_DELETE_WINDOW', close); poll(); app.mainloop()

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--test-cli':
        # Packaged executable integration checks; no implicit game path.
        try:
            result = operate(sys.argv[3], sys.argv[2]); code = 0
        except Exception as e: result = str(e); code = 1
        Path(sys.argv[4]).write_text(json.dumps({'code': code, 'message': result}, ensure_ascii=False), encoding='utf8')
        sys.exit(code)
    else: gui()
