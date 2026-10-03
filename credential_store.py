"""Store the Gemini API key in Windows Credential Manager."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import os

from brand import BRAND

TARGET = BRAND.credential_target
MAX_GEMINI_KEYS = 5
TARGETS = tuple(
    TARGET if index == 1 else f"{TARGET}/{index}"
    for index in range(1, MAX_GEMINI_KEYS + 1)
)
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2


class CredentialError(OSError):
    pass


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", w.DWORD),
        ("Type", w.DWORD),
        ("TargetName", w.LPWSTR),
        ("Comment", w.LPWSTR),
        ("LastWritten", w.FILETIME),
        ("CredentialBlobSize", w.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", w.DWORD),
        ("AttributeCount", w.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", w.LPWSTR),
        ("UserName", w.LPWSTR),
    ]


def _advapi():
    if os.name != "nt":
        raise CredentialError("Windows Credential Manager is unavailable")
    api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    api.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), w.DWORD]
    api.CredWriteW.restype = w.BOOL
    api.CredReadW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD,
                              ctypes.POINTER(ctypes.POINTER(_CREDENTIALW))]
    api.CredReadW.restype = w.BOOL
    api.CredDeleteW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD]
    api.CredDeleteW.restype = w.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    return api


def read_target(target):
    api = _advapi()
    ptr = ctypes.POINTER(_CREDENTIALW)()
    if not api.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(ptr)):
        error = ctypes.get_last_error()
        if error == 1168:  # ERROR_NOT_FOUND
            return ""
        raise CredentialError(error, ctypes.FormatError(error))
    try:
        row = ptr.contents
        if not row.CredentialBlob or not row.CredentialBlobSize:
            return ""
        raw = ctypes.string_at(row.CredentialBlob, row.CredentialBlobSize)
        return raw.decode("utf-16-le")
    finally:
        api.CredFree(ptr)


def write_target(target, secret):
    secret = str(secret or "")
    if not secret:
        delete_target(target)
        return
    api = _advapi()
    raw = secret.encode("utf-16-le")
    blob = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    row = _CREDENTIALW()
    row.Type = CRED_TYPE_GENERIC
    row.TargetName = target
    row.CredentialBlobSize = len(raw)
    row.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
    row.Persist = CRED_PERSIST_LOCAL_MACHINE
    row.UserName = BRAND.name
    if not api.CredWriteW(ctypes.byref(row), 0):
        error = ctypes.get_last_error()
        raise CredentialError(error, ctypes.FormatError(error))


def delete_target(target):
    api = _advapi()
    if not api.CredDeleteW(target, CRED_TYPE_GENERIC, 0):
        error = ctypes.get_last_error()
        if error != 1168:
            raise CredentialError(error, ctypes.FormatError(error))


def read():
    return read_target(TARGET)


def write(secret):
    return write_target(TARGET, secret)


def delete():
    return delete_target(TARGET)


def read_all():
    """Return configured Gemini keys in failover order."""
    keys = []
    for target in TARGETS:
        secret = read_target(target).strip()
        if secret and secret not in keys:
            keys.append(secret)
    return keys


def write_all(secrets):
    """Replace the ordered keyring, restoring the old values on failure.

    Returns True when slots were written, False when the stored values
    already matched (no Credential Manager writes issued).
    """
    normalized = []
    for value in secrets:
        secret = str(value or "").strip()
        if secret and secret not in normalized:
            normalized.append(secret)
    if len(normalized) > MAX_GEMINI_KEYS:
        raise CredentialError(f"At most {MAX_GEMINI_KEYS} Gemini API keys are supported")

    previous = [read_target(target) for target in TARGETS]
    desired = normalized + [""] * (len(TARGETS) - len(normalized))
    if [(value or "").strip() for value in previous] == desired:
        return False
    try:
        for target, secret in zip(TARGETS, desired):
            if secret:
                write_target(target, secret)
            else:
                delete_target(target)
        verified = [read_target(target) for target in TARGETS]
        if verified != desired:
            raise CredentialError("Gemini API keys could not be verified")
        return True
    except Exception as exc:
        for target, secret in zip(TARGETS, previous):
            try:
                if secret:
                    write_target(target, secret)
                else:
                    delete_target(target)
            except CredentialError:
                pass
        if isinstance(exc, CredentialError):
            raise
        raise CredentialError(str(exc)) from exc


class CredentialStore:
    read = staticmethod(read)
    write = staticmethod(write)
    delete = staticmethod(delete)
    read_target = staticmethod(read_target)
    write_target = staticmethod(write_target)
    delete_target = staticmethod(delete_target)
    read_all = staticmethod(read_all)
    write_all = staticmethod(write_all)
