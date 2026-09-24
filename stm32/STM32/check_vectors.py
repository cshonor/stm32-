#!/usr/bin/env python3
# check_vectors.py —— 通用版向量表断言
#
# 和 stm32/01-startup/check_vectors.py 的分工：
#   stm32/01 那份是「严格版」：手写启动文件时 24 项的符号名都是我自己起的，
#                             所以能逐项比对 NMI_Handler / SVC_Handler ...
#   这一份是「通用版」：向量表现在在库里（lib/cm3/vector.c），handler 由
#                       irq2nvic_h 从 irq.json 生成，命名规则不同、项数也随芯片变，
#                       而且——实测发现——libopencm3 的链接脚本把 .vectors
#                       输入段 KEEP 进了 .text 输出段，ELF 里根本没有独立的
#                       "向量表段"。所以改为：
#                         1) 先找独立段（.vectors / .isr_vector）
#                         2) 找不到就找一个数据符号（vector_table 等）并用它的
#                            nm 尺寸（libopencm3 的 vector_table 有 336 = 84 项）
#                         3) 从镜像里按 VMA 切片，校验「结构不变量」，不认符号名
#
# 用法：
#   python3 check_vectors.py blink.elf
#   python3 check_vectors.py --tools gnu blink.elf     # 强制 arm-none-eabi-*
#   python3 check_vectors.py --tools llvm blink.elf    # 强制 llvm-*
#   python3 check_vectors.py --rom 0x08000000 blink.elf
#
# 只依赖 binutils / llvm 的 objdump、objcopy、nm，纯主机侧，不需要板子。

import os
import shutil
import struct
import subprocess
import sys

USAGE = "用法: check_vectors.py [--tools gnu|llvm] [--rom 0x08000000] <elf>..."

# 候选①：独立的向量表段名（stm32/01 手写的叫 .isr_vector，libopencm3 的输入段叫 .vectors）
SECTION_CANDIDATES = [".isr_vector", ".vectors", ".vector_table"]
# 候选②：向量表符号名（当段被合并进 .text 时只能靠符号定位）
SYMBOL_CANDIDATES = ["vector_table", "g_vectors", "vectors", "_vectors"]

# ARMv7-M / ARMv6-M 的架构保留槽位（不是中断，硬件永远不会跳到这里）
RESERVED_SLOTS = {7, 8, 9, 10, 13}

TOOL_SETS = {
    "gnu":  ["arm-none-eabi-objdump", "arm-none-eabi-objcopy", "arm-none-eabi-nm"],
    "llvm": ["llvm-objdump", "llvm-objcopy", "llvm-nm"],
}


def pick_tools(force=None):
    """优先 GNU（arm-none-eabi-*），退回 LLVM。"""
    for name in ([force] if force else ["gnu", "llvm"]):
        cmd = TOOL_SETS[name]
        if all(shutil.which(c) for c in cmd):
            return name, cmd
    return None, None


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def sections_of(objdump, elf):
    """返回 [(名字, size, vma, lma, is_loaded)]。objdump -h 每个段占两行。"""
    _, out, _ = run([objdump, "-h", elf])
    lines = out.splitlines()
    secs = []
    for i, line in enumerate(lines):
        p = line.split()
        if len(p) >= 7 and p[0].rstrip(":").isdigit():
            flags = lines[i + 1] if i + 1 < len(lines) else ""
            secs.append((p[1], int(p[2], 16), int(p[3], 16), int(p[4], 16),
                         ("CONTENTS" in flags and "ALLOC" in flags)))
    return secs


def symbols_of(nm, elf):
    """符号表 -> (名字->地址, 地址->名字, 名字->尺寸)"""
    by_name, by_addr, size_of = {}, {}, {}
    _, out, _ = run([nm, "-n", "--print-size", elf])
    for line in out.splitlines():
        p = line.split()
        if len(p) == 4:                      # addr size type name
            addr, size, name = int(p[0], 16), int(p[1], 16), p[3]
            size_of[name] = size
        elif len(p) == 3 and p[1] in "TtDdBbRrAaWwVv":
            addr, name = int(p[0], 16), p[2]
        else:
            continue
        by_name[name] = addr
        by_addr.setdefault(addr, name)
    return by_name, by_addr, size_of


def raw_bytes(objcopy, elf, section=None):
    tmp = "/tmp/_vec_%s_%s.bin" % (os.path.basename(elf), (section or "all").strip("."))
    cmd = [objcopy, "-O", "binary"]
    if section:
        cmd += ["--only-section", section]
    cmd += [elf, tmp]
    if run(cmd)[0] != 0 or not os.path.exists(tmp):
        return None
    with open(tmp, "rb") as f:
        return f.read()


def words_of(data):
    if not data:
        return []
    return list(struct.unpack("<%dI" % (len(data) // 4), data[: len(data) // 4 * 4]))


def locate_table(objdump, elf, secs, syms, sizes):
    """定位向量表，返回 (来源说明, vma, size)。"""
    for name, size, vma, _lma, loaded in secs:
        if name in SECTION_CANDIDATES and size > 0:
            return "段 %s" % name, vma, size
    for name in SYMBOL_CANDIDATES:
        if name in syms and sizes.get(name, 0) > 0:
            return "符号 %s（nm 尺寸）" % name, syms[name], sizes[name]
    return None, None, 0


def check(elf, tools, rom):
    objdump, objcopy, nm = tools
    print("=== %s ===" % elf)
    fails, warns = [], []

    def ok(m):   print("[ok]   " + m)
    def bad(m):  print("[FAIL] " + m); fails.append(m)
    def warn(m): print("[warn] " + m); warns.append(m)

    secs = sections_of(objdump, elf)
    syms, by_addr, sizes = symbols_of(nm, elf)

    src, vma, size = locate_table(objdump, elf, secs, syms, sizes)
    if src is None:
        bad("找不到向量表：没有独立的 %s 段，也没有 %s 符号"
            % ("/".join(SECTION_CANDIDATES), "/".join(SYMBOL_CANDIDATES)))
        return fails, warns
    ok("向量表来源：%s @ 0x%08X，%d 字节" % (src, vma, size))

    # 镜像基址 = 所有「有内容」的段里最小的 LMA（.data 的 LMA 会跟在 .text 后面）
    loaded = [s for s in secs if s[4] and s[1] > 0]
    if not loaded:
        bad("ELF 里没有可加载段（CONTENTS），拿不到镜像")
        return fails, warns
    base = min(s[3] for s in loaded)

    if vma == rom:
        ok("向量表就在 Flash 首地址 0x%08X（硬件复位后取 MSP/PC 的地方）" % rom)
    else:
        bad("向量表 @ 0x%08X ≠ Flash 首地址 0x%08X —— 硬件取不到 MSP/PC" % (vma, rom))

    img = raw_bytes(objcopy, elf)
    if img is None:
        bad("objcopy 取镜像失败")
        return fails, warns
    off = vma - base
    if off < 0 or off + size > len(img):
        bad("镜像只有 %d 字节，切不出 [0x%X,0x%X)" % (len(img), off, off + size))
        return fails, warns
    words = words_of(img[off: off + size])
    ok("镜像 0x%08X..0x%08X 切出 %d 项（%d 字节）"
       % (vma, vma + size, len(words), size))

    estack = syms.get("_stack", syms.get("_estack"))
    if estack is None:
        warn("符号表里没有 _stack/_estack，跳过 MSP 校验")
    elif words[0] == estack:
        ok("[ 0] 0x%08X == _stack          ← 上电装进 MSP" % words[0])
    else:
        bad("[ 0] 0x%08X != _stack(0x%08X) —— 上电会把别的值当栈顶" % (words[0], estack))

    if words[1] & 1:
        ok("[ 1] 0x%08X -> %-18s (thumb=1)" % (words[1], by_addr.get(words[1] & ~1, "?")))
    else:
        bad("[ 1] 0x%08X 的 bit0=0：不是 Thumb 地址，异常进入时 INVSTATE" % words[1])

    zero_slots, bad_thumb, blocking = [], [], 0
    blk = syms.get("blocking_handler")
    for i, w in enumerate(words):
        if i < 2:
            continue
        if i in RESERVED_SLOTS:
            if w != 0:
                bad("[%2d] 0x%08X != 0：架构保留位必须为 0" % (i, w))
            continue
        if w == 0:
            zero_slots.append(i)
            continue
        if (w & 1) == 0:
            bad_thumb.append(i)
        if blk is not None and (w & ~1) == (blk & ~1):
            blocking += 1

    if zero_slots:
        warn("%d 个非保留槽位为 0：%s" % (len(zero_slots), zero_slots[:8]))
    else:
        ok("非保留槽位全部非 0（每个 IRQ 都有入口）")
    if bad_thumb:
        bad("%d 个槽位的 bit0=0（不是 Thumb 地址）：%s" % (len(bad_thumb), bad_thumb[:8]))
    else:
        ok("所有入口的 bit0 都是 1（Thumb 状态，硬件跳转前自动切状态）")
    if blk is not None:
        ok("%d 个槽位指向 blocking_handler(0x%08X)：库里没实现的中断兜底"
           % (blocking, blk))

    # 镜像头两字必须就是向量表前两项（否则说明前面还塞了别的东西）
    head = words_of(img[:8])
    if len(head) >= 2:
        if head[0] == words[0] and head[1] == words[1]:
            ok("镜像前 8 字节 == 向量表前两项（0x%08X 处的第 0 个字就是栈顶）" % rom)
        else:
            bad("镜像开头(0x%08X,0x%08X) != 向量表前两项(0x%08X,0x%08X)"
                % (head[0], head[1], words[0], words[1]))

    return fails, warns


def main(argv):
    args, tools_force, rom = argv[1:], None, 0x08000000
    while args and args[0].startswith("--"):
        if args[0] == "--tools":
            tools_force = args[1]; args = args[2:]
        elif args[0] == "--rom":
            rom = int(args[1], 0); args = args[2:]
        else:
            print(USAGE); return 2
    if not args:
        print(USAGE); return 2

    toolname, tools = pick_tools(tools_force)
    if tools is None:
        print("找不到 objdump/objcopy/nm：装 arm-none-eabi 工具链，"
              "或把 llvm 工具放进 PATH")
        return 2
    print("工具集：%s (%s)\n" % (toolname, tools[0]))

    rc = 0
    for elf in args:
        fails, warns = check(elf, tools, rom)
        print("--- 结论：%s（%d 项失败 / %d 项警告）---\n"
              % ("通过" if not fails else "失败", len(fails), len(warns)))
        rc |= 1 if fails else 0
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
