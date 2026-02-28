"""
beyondmem.py - MemFurqan (uses bytes.find for scanning - PROVEN FAST)
"""
import ctypes, ctypes.wintypes, os, struct, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

PROCESS_ALL_ACCESS=0x1F0FFF; MEM_COMMIT=0x1000; MEM_PRIVATE=0x20000; MEM_IMAGE=0x1000000
PAGE_NOACCESS=0x01; PAGE_READONLY=0x02; PAGE_READWRITE=0x04; PAGE_WRITECOPY=0x08
PAGE_EXECUTE=0x10; PAGE_EXECUTE_READ=0x20; PAGE_EXECUTE_READWRITE=0x40
PAGE_EXECUTE_WRITECOPY=0x80; PAGE_GUARD=0x100

class SYSTEM_INFO(ctypes.Structure):
    _fields_=[("arch",ctypes.wintypes.WORD),("_r",ctypes.wintypes.WORD),
        ("pageSize",ctypes.wintypes.DWORD),("minAddr",ctypes.c_uint64),("maxAddr",ctypes.c_uint64),
        ("mask",ctypes.c_uint64),("nProc",ctypes.wintypes.DWORD),("pType",ctypes.wintypes.DWORD),
        ("allocGran",ctypes.wintypes.DWORD),("pLevel",ctypes.wintypes.WORD),("pRev",ctypes.wintypes.WORD)]

class MBI64(ctypes.Structure):
    _fields_=[("BaseAddress",ctypes.c_uint64),("AllocationBase",ctypes.c_uint64),
        ("AllocationProtect",ctypes.wintypes.DWORD),("_a1",ctypes.wintypes.DWORD),
        ("RegionSize",ctypes.c_uint64),("State",ctypes.wintypes.DWORD),
        ("Protect",ctypes.wintypes.DWORD),("Type",ctypes.wintypes.DWORD),("_a2",ctypes.wintypes.DWORD)]

_k32=ctypes.windll.kernel32
_k32.GetSystemInfo.argtypes=[ctypes.POINTER(SYSTEM_INFO)]; _k32.GetSystemInfo.restype=None
_k32.OpenProcess.argtypes=[ctypes.wintypes.DWORD,ctypes.wintypes.BOOL,ctypes.wintypes.DWORD]; _k32.OpenProcess.restype=ctypes.c_void_p
_k32.CloseHandle.argtypes=[ctypes.c_void_p]; _k32.CloseHandle.restype=ctypes.wintypes.BOOL
_k32.ReadProcessMemory.argtypes=[ctypes.c_void_p,ctypes.c_uint64,ctypes.c_void_p,ctypes.c_uint64,ctypes.POINTER(ctypes.c_uint64)]
_k32.ReadProcessMemory.restype=ctypes.wintypes.BOOL
_k32.WriteProcessMemory.argtypes=[ctypes.c_void_p,ctypes.c_uint64,ctypes.c_void_p,ctypes.c_uint64,ctypes.POINTER(ctypes.c_uint64)]
_k32.WriteProcessMemory.restype=ctypes.wintypes.BOOL
_k32.VirtualQueryEx.argtypes=[ctypes.c_void_p,ctypes.c_uint64,ctypes.c_void_p,ctypes.c_uint64]; _k32.VirtualQueryEx.restype=ctypes.c_uint64
_k32.IsWow64Process.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.wintypes.BOOL)]; _k32.IsWow64Process.restype=ctypes.wintypes.BOOL
_psapi=ctypes.windll.psapi
_psapi.EnumProcessModulesEx.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.wintypes.DWORD,ctypes.POINTER(ctypes.wintypes.DWORD),ctypes.wintypes.DWORD]
_psapi.EnumProcessModulesEx.restype=ctypes.wintypes.BOOL
_psapi.GetModuleBaseNameW.argtypes=[ctypes.c_void_p,ctypes.c_uint64,ctypes.c_wchar_p,ctypes.wintypes.DWORD]; _psapi.GetModuleBaseNameW.restype=ctypes.wintypes.DWORD

def enable_vt():
    try:
        k=ctypes.windll.kernel32; k.GetStdHandle.restype=ctypes.c_void_p
        k.GetConsoleMode.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
        k.SetConsoleMode.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
        h=k.GetStdHandle(-11); m=ctypes.c_ulong()
        k.GetConsoleMode(h,ctypes.byref(m)); k.SetConsoleMode(h,m.value|0x0005)
    except: pass

class MemFurqan:
    def __init__(self):
        self.p_handle=None; self.the_proc_id=0; self.the_proc_name=""; self.is_64bit=False
        self.main_module_base=0; self.modules:Dict[str,int]={}
    @property
    def theProc(self):
        if not self.the_proc_id: return None
        class P: pass
        p=P(); p.ProcessName=self.the_proc_name; p.Id=self.the_proc_id; return p
    @staticmethod
    def is_admin():
        try: return ctypes.windll.shell32.IsUserAnAdmin()!=0
        except: return False
    def open_process(self, pid):
        if pid<=0: return False
        if self.the_proc_id==pid and self.p_handle: return True
        try:
            import psutil; p=psutil.Process(pid); self.the_proc_name=p.name().replace(".exe",""); self.the_proc_id=pid
        except: self.the_proc_name=f"PID_{pid}"; self.the_proc_id=pid
        h=_k32.OpenProcess(PROCESS_ALL_ACCESS,True,pid)
        if not h: return False
        self.p_handle=h
        w=ctypes.wintypes.BOOL(False); _k32.IsWow64Process(h,ctypes.byref(w))
        import platform; self.is_64bit=(platform.machine().endswith('64') and not w.value)
        self._get_modules(); return True
    def open_process_by_name(self, name):
        import psutil; nl=name.lower()
        if not nl.endswith(".exe"): nl+=".exe"
        for p in psutil.process_iter(['pid','name']):
            try:
                if p.info['name'].lower()==nl: return self.open_process(p.info['pid'])
            except: continue
        return False
    def close_process(self):
        if self.p_handle: _k32.CloseHandle(self.p_handle); self.p_handle=None; self.the_proc_id=0
    def _get_modules(self):
        self.modules.clear()
        try:
            hm=(ctypes.c_uint64*1024)(); cb=ctypes.wintypes.DWORD()
            if not _psapi.EnumProcessModulesEx(self.p_handle,ctypes.byref(hm),ctypes.sizeof(hm),ctypes.byref(cb),0x03): return
            for i in range(cb.value//8):
                b=ctypes.create_unicode_buffer(260); _psapi.GetModuleBaseNameW(self.p_handle,hm[i],b,260)
                if b.value and b.value not in self.modules: self.modules[b.value]=hm[i]
                if i==0: self.main_module_base=hm[i]
        except: pass

    def _read_raw(self, addr, size):
        if size<=0 or not self.p_handle: return None
        try:
            buf=ctypes.create_string_buffer(size); n=ctypes.c_uint64(0)
            if not _k32.ReadProcessMemory(self.p_handle,ctypes.c_uint64(addr),buf,ctypes.c_uint64(size),ctypes.byref(n)) or n.value==0: return None
            return buf.raw[:n.value]
        except: return None
    def _write_raw(self, addr, data):
        try:
            buf=ctypes.create_string_buffer(data,len(data)); n=ctypes.c_uint64(0)
            return bool(_k32.WriteProcessMemory(self.p_handle,ctypes.c_uint64(addr),buf,ctypes.c_uint64(len(data)),ctypes.byref(n)))
        except: return False
    def read_bytes(self, addr, length): return self._read_raw(addr, length)
    def read_int32(self, addr):
        d=self._read_raw(addr,4); return struct.unpack("<i",d)[0] if d and len(d)>=4 else None
    def write_int32(self, addr, val): return self._write_raw(addr, struct.pack("<i",val))
    def WriteMemory(self, code, type_str, write, file=""):
        addr=self.get_code(code,file,8); t=type_str.lower()
        if t=="int": data=struct.pack("<i",int(write))
        elif t=="float": data=struct.pack("<f",float(write))
        else: return False
        return self._write_raw(addr,data)
    def get_code(self, name, path="", size=8):
        text=name.replace(" ","")
        if not text: return 0
        try: return int(text,16)
        except: return 0

    # ============================================
    #  AoB Scan - bytes.find() (PROVEN APPROACH)
    # ============================================

    @staticmethod
    def _parse_aob(search):
        tokens=search.strip().split(); pat=bytearray(len(tokens)); mask=bytearray(len(tokens))
        for i,t in enumerate(tokens):
            if t in("??","?"): mask[i]=0
            else: mask[i]=0xFF; pat[i]=int(t,16)
        return bytes(pat),bytes(mask)

    @staticmethod
    def _build_scanner(pat, mask):
        """Extract fixed prefix and suffix for bytes.find()."""
        n=len(pat)
        # Longest fixed prefix
        pe=0
        for i in range(n):
            if mask[i]!=0xFF: break
            pe=i+1
        # Fixed suffix from end
        ss=n
        for i in range(n-1,-1,-1):
            if mask[i]!=0xFF: ss=i+1; break
        return bytes(pat[:pe]), bytes(pat[ss:]), ss, n

    def _scan_chunk(self, addr, size, prefix, suffix, suffix_off, pat_len):
        """Read chunk + search with bytes.find(). One call = entire search in C."""
        data = self._read_raw(addr, size)
        if not data:
            return []
        results = []
        dlen = len(data)
        end = dlen - pat_len
        slen = len(suffix)
        pos = 0
        while pos <= end:
            idx = data.find(prefix, pos, end + len(prefix))
            if idx == -1:
                break
            # Verify suffix
            if not slen or data[idx+suffix_off:idx+suffix_off+slen] == suffix:
                results.append(addr + idx)
            pos = idx + 1
        return results

    def AoBScan(self, start, end, search, readable=True, writable=True, executable=True, file="", progress_cb=None):
        pat, mask = self._parse_aob(search)
        prefix, suffix, suffix_off, pat_len = self._build_scanner(pat, mask)

        si=SYSTEM_INFO(); _k32.GetSystemInfo(ctypes.byref(si))
        mna=si.minAddr or 0x10000; mxa=si.maxAddr or 0x7FFFFFFEFFFF
        if start<mna: start=mna
        if end>mxa: end=mxa

        # Enumerate + merge regions
        regions=[]; cur=start
        while cur<end:
            raw=MBI64(); ret=_k32.VirtualQueryEx(self.p_handle,ctypes.c_uint64(cur),ctypes.byref(raw),ctypes.c_uint64(ctypes.sizeof(raw)))
            if ret==0 or raw.RegionSize==0 or raw.BaseAddress+raw.RegionSize<=cur: break
            ok=(raw.State==MEM_COMMIT) and (raw.BaseAddress<mxa) and not(raw.Protect&PAGE_GUARD) and not(raw.Protect&PAGE_NOACCESS)
            ok=ok and (raw.Type==MEM_PRIVATE or raw.Type==MEM_IMAGE)
            if ok:
                r=(raw.Protect&PAGE_READONLY)>0
                w=raw.Protect&(PAGE_READWRITE|PAGE_WRITECOPY|PAGE_EXECUTE_READWRITE|PAGE_EXECUTE_WRITECOPY)>0
                x=raw.Protect&(PAGE_EXECUTE|PAGE_EXECUTE_READ|PAGE_EXECUTE_READWRITE|PAGE_EXECUTE_WRITECOPY)>0
                ok=ok and ((r and readable)or(w and writable)or(x and executable))
            if not ok: cur=raw.BaseAddress+raw.RegionSize; continue
            base=cur; sz=raw.RegionSize; rbase=raw.BaseAddress; cur=raw.BaseAddress+raw.RegionSize
            if regions:
                lb,ls,lr=regions[-1]
                if lr+ls==raw.BaseAddress: regions[-1]=(lb,ls+raw.RegionSize,lr); continue
            regions.append((base,sz,rbase))

        # Split into 64MB chunks for thread balancing
        CHUNK=64*1024*1024; chunks=[]
        for base,sz,_ in regions:
            if sz<=CHUNK:
                chunks.append((base,sz))
            else:
                off=0
                while off<sz:
                    cs=min(CHUNK,sz-off); chunks.append((base+off,cs))
                    adv=cs-pat_len+1
                    if adv<=0: break
                    off+=adv

        tc=len(chunks); results=[]; done_count=[0]; lock=threading.Lock()
        workers=min(os.cpu_count() or 4, 12)

        def do(a,s):
            return self._scan_chunk(a, s, prefix, suffix, suffix_off, pat_len)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs={pool.submit(do,a,s):i for i,(a,s) in enumerate(chunks)}
            for f in as_completed(futs):
                with lock: done_count[0]+=1; dc=done_count[0]
                try:
                    h=f.result()
                    if h: results.extend(h)
                except: pass
                if progress_cb: progress_cb(dc, tc, len(results))

        results.sort()
        return results
