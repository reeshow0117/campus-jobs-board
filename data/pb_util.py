#!/usr/bin/env python3
"""通用 protobuf wire-format 解析器（无 schema），用于解析腾讯文档普通表格数据"""

def read_varint(buf, pos):
    shift = 0
    result = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos

def parse_fields(buf):
    """返回 [(field_no, wire_type, value)]；wire2 的 value 保留 bytes"""
    out = []
    pos = 0
    n = len(buf)
    while pos < n:
        key, pos = read_varint(buf, pos)
        fno, wt = key >> 3, key & 7
        if wt == 0:
            v, pos = read_varint(buf, pos)
            out.append((fno, wt, v))
        elif wt == 2:
            ln, pos = read_varint(buf, pos)
            out.append((fno, wt, buf[pos:pos+ln]))
            pos += ln
        elif wt == 5:
            out.append((fno, wt, buf[pos:pos+4]))
            pos += 4
        elif wt == 1:
            out.append((fno, wt, buf[pos:pos+8]))
            pos += 8
        else:
            raise ValueError(f"unsupported wire type {wt} at {pos}")
    return out

def looks_like_message(b):
    """启发式：bytes 是否为嵌套 message"""
    if not b or len(b) < 2:
        return False
    try:
        parse_fields(b)
        return True
    except Exception:
        return False

def try_decode_str(b):
    try:
        s = b.decode('utf-8')
        if all(ch.isprintable() or ch in '\n\t\r' for ch in s):
            return s
    except Exception:
        pass
    return None
