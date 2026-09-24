#!/usr/bin/env python3
# check_vectors.py —— 不用板子，断言"上电那一刻硬件会读到什么"
#
# 为什么这件事值得单独写脚本：
#   向量表是整个程序里**唯一一段被硬件当作输入**的数据。
#   代码写错了，CPU 一定跑给你看；向量表写错了，CPU 上电就疯了，
#   而且不会有任何编译/链接期提示（见 linker-nokeep.ld 的实测）。
#   所以它需要断言，就像业务代码需要单测。
#
# 用法（在 stm32/01-bare-metal 下）：
#   python3 check_vectors.py blink_asm.elf blink_c.elf          # 逐项校验
#   python3 check_vectors.py --expect-fail blink_asm_nokeep.elf # 反面教材：预期它挂
#   python3 check_vectors.py --diff blink_asm.elf blink_c.elf   # 对比两种写法
#
# 只依赖 llvm 工具（objdump 读段表 / objcopy 取字节 / nm 取符号），
# 纯主机侧，不需要 ST-Link，也不需要装任何 Python 包。

import os
import shutil
import struct
import subprocess
import sys

USAGE = ("用法: check_vectors.py [--expect-fail] <elf>...\n"
         "      check_vectors.py --diff <elf_a> <elf_b>")

FLASH_ORIGIN = 0x08000000

# 向量表期望布局：24 项
#   ("stack", None)          第 0 项是数据（MSP 初值）
#   ("handler", <符号名>)     异常/中断入口（bit0 必须为 1 = Thumb）
#   ("zero", None)           架构保留位，必须恰好为 0
EXPECTED = [
    ("stack",   None),
    ("handler", "Reset_Handler"),
    ("handler", "NMI_Handler"),
    ("handler", "HardFault_Handler"),
    ("handler", "MemManage_Handler"),
    ("handler", "BusFault_Handler"),
    ("handler", "UsageFault_Handler"),
    ("zero",    None),
    ("zero",    None),
    ("zero",    None),
    ("zero",    None),
    ("handler", "SVC_Handler"),
    ("handler", "DebugMon_Handler"),
    ("zero",    None),
    ("handler", "PendSV_Handler"),
    ("handler", "SysTick_Handler"),
    ("handler", "WWDG_IRQHandler"),
    ("handler", "PVD_IRQHandler"),
    ("handler", "TAMPER_IRQHandler"),
    ("handler", "RTC_IRQHandler"),
    ("handler", "FLASH_IRQHandler"),
    ("handler", "RCC_IRQHandler"),
    ("handler", "EXTI0_IRQHandler"),
    ("handler", "EXTI1_IRQHandler"),
]

TOOLS = ["llvm-objdump", "llvm-objcopy", "llvm-nm"]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def raw_bytes(elf, section=None):
    """取字节：section=None 表示整个镜像（-O binary）"""
    tmp = "/tmp/_vec_%s.bin" % os.path.basename(elf)
    cmd = ["llvm-objcopy", "-O", "binary"]
    if section:
        cmd += ["--only-section", section]
    cmd += [elf, tmp]
    rc, _, err = run(cmd)
    if rc != 0:
        return None
    with open(tmp, "rb") as f:
        return f.read()


def words_of(data):
    if not data:
        return []
    return list(struct.unpack("<%dI" % (len(data) // 4), data[: len(data) // 4 * 4]))


def section_of(elf, name):
    """返回 (vma, size)；段不存在返回 (None, 0)"""
    _, out, _ = run(["llvm-objdump", "-h", elf])
    for line in out.splitlines():
        p = line.split()
        if len(p) >= 5 and p[1] == name:
            return int(p[3], 16), int(p[2], 16)
    return None, 0


def symbols_of(elf):
    syms = {}
    _, out, _ = run(["llvm-nm", "-n", "--print-size", elf])
    for line in out.splitlines():
        p = line.split()
        if not p:
            continue
        if len(p) == 4:                                   # addr size type name
            syms[p[3]] = int(p[0], 16)
        elif len(p) == 3 and p[1] in "TtDdBbRrAaWwVv":    # addr type name
            syms[p[2]] = int(p[0], 16)
    return syms


def check(elf, expect_fail=False):
    print("=== %s ===" % elf)
    fails = []

    def ok(msg):
        print("[ok]   " + msg)

    def bad(msg):
        print("[FAIL] " + msg)
        fails.append(msg)

    syms = symbols_of(elf)
    estack = syms.get("_estack")
    vma, size = section_of(elf, ".isr_vector")

    # ---- 情况 0：向量表段没了（linker-nokeep.ld 的实验）---------------
    if vma is None or size == 0:
        bad(".isr_vector %s" % ("段不存在" if vma is None else "段长为 0 —— 被 --gc-sections 丢掉了"))
        img = words_of(raw_bytes(elf))
        if img and len(img) >= 2:
            print("       硬件按 0x%08X 上电取指时实际读到：SP <- 0x%08X, PC <- 0x%08X"
                  % (FLASH_ORIGIN, img[0], img[1]))
            print("       （正常应当是 SP <- 0x%08X = _estack，PC <- Reset_Handler）"
                  % (estack if estack is not None else 0))
            print("       这两个值现在是代码指令 —— CPU 会拿指令字当栈顶用，上电即崩。")
        return verdict(fails, expect_fail)

    words = words_of(raw_bytes(elf, ".isr_vector"))

    # ---- 1. 位置：必须在 Flash 首地址 ---------------------------------
    if vma == FLASH_ORIGIN:
        ok(".isr_vector @ 0x%08X，%d 项（%d 字节）" % (vma, len(words), size))
    else:
        bad(".isr_vector @ 0x%08X，不是 Flash 首地址 0x%08X —— 硬件取不到 MSP/PC"
            % (vma, FLASH_ORIGIN))

    # ---- 2. 表长：至少 16 项系统异常 ---------------------------------
    if len(words) >= 16:
        ok("表长 %d 项 >= 16（系统异常全能放下）" % len(words))
    else:
        bad("表长只有 %d 项，连系统异常都不够" % len(words))

    # ---- 3. 逐项 -----------------------------------------------------
    for i, (kind, name) in enumerate(EXPECTED):
        if i >= len(words):
            bad("[%2d] 缺项（期望 %s）" % (i, kind))
            continue
        w = words[i]
        if kind == "stack":
            if estack is not None and w == estack:
                ok("[%2d] 0x%08X == _estack     ← 上电装进 MSP" % (i, w))
            else:
                bad("[%2d] 0x%08X != _estack(0x%08X) —— 上电会把别的值当栈顶"
                    % (i, w, estack if estack is not None else 0))
        elif kind == "zero":
            if w == 0:
                ok("[%2d] 0x00000000           ← 架构保留位" % i)
            else:
                bad("[%2d] 0x%08X != 0，保留位必须为 0" % (i, w))
        else:
            addr = syms.get(name)
            if addr is None:
                bad("[%2d] 符号 %s 不存在" % (i, name))
            elif (w & 0xFFFFFFFE) != (addr & 0xFFFFFFFE):
                bad("[%2d] 0x%08X 不指向 %s(0x%08X)" % (i, w, name, addr))
            elif (w & 1) == 0:
                bad("[%2d] 0x%08X 的 bit0 = 0：不是 Thumb 地址，异常进入时会 INVSTATE" % (i, w))
            else:
                tag = " (弱别名 -> Default_Handler)" if addr == syms.get("Default_Handler") else ""
                ok("[%2d] 0x%08X -> %-20s (0x%08X, thumb=1)%s" % (i, w, name, addr, tag))

    # ---- 4. 烧进 Flash 的镜像，开头也得是一样的两个字 -----------------
    img = words_of(raw_bytes(elf))
    if len(img) >= 2:
        if img[0] == words[0] and img[1] == words[1]:
            ok("镜像前 8 字节 == 向量表前 8 字节（烧到 0x%08X 的第 0 个字就是栈顶）"
               % FLASH_ORIGIN)
        else:
            bad("镜像开头(0x%08X,0x%08X) 与向量表前两项(0x%08X,0x%08X) 不一致 —— "
                "向量表前面还有别的东西，硬件读到的不是它"
                % (img[0], img[1], words[0], words[1]))

    return verdict(fails, expect_fail)


def verdict(fails, expect_fail):
    if not fails:
        print("--- 结论：通过 ---")
        if expect_fail:
            print("（--expect-fail：本该失败却通过了 —— 实验前提不成立，去查原因）")
            return 1
        return 0
    print("--- 结论：失败 %d 项 ---" % len(fails))
    if expect_fail:
        print("（--expect-fail：如预期地失败了，这正是本实验要看的现象）")
        return 0
    return 1


def diff(a, b):
    print("=== 向量表语义对比：%s vs %s ===" % (a, b))
    wa = words_of(raw_bytes(a, ".isr_vector"))
    wb = words_of(raw_bytes(b, ".isr_vector"))
    if len(wa) != len(wb) or not wa:
        print("[FAIL] 两边项数不同或取不到：%d vs %d" % (len(wa), len(wb)))
        return 1
    sa, sb = symbols_of(a), symbols_of(b)
    default_a, default_b = sa.get("Default_Handler"), sb.get("Default_Handler")

    different = [i for i in range(len(wa)) if wa[i] != wb[i]]
    print("项数：%d（一致）" % len(wa))
    print("字节不同的项：%d 项 —— 全是 handler 的落位地址，不是语义差异" % len(different))
    for i in different:
        name = EXPECTED[i][1] if EXPECTED[i][0] == "handler" else "?"
        def mark(w, d):
            if d is not None and (w & 0xFFFFFFFE) == (d & 0xFFFFFFFE):
                return "转到 Default_Handler"
            return "有独立实现"
        print("  [%2d] %-20s asm=0x%08X (%s) | c=0x%08X (%s)"
              % (i, name, wa[i], mark(wa[i], default_a), wb[i], mark(wb[i], default_b)))

    same = all(
        (kind == "zero" and wa[i] == 0 and wb[i] == 0)
        or (kind == "stack" and wa[i] == wb[i])
        or (kind == "handler"
            and (wa[i] & 0xFFFFFFFE) == (sa.get(name, -2) & 0xFFFFFFFE)
            and (wa[i] & 1) == 1
            and (wb[i] & 0xFFFFFFFE) == (sb.get(name, -2) & 0xFFFFFFFE)
            and (wb[i] & 1) == 1)
        for i, (kind, name) in enumerate(EXPECTED)
    )
    print("--- 结论：%s ---" % ("两种写法语义完全一致（24 项逐项等价），"
                              "差异只在 handler 落在哪个地址 —— 那是代码长度不同造成的"
                              if same else "语义不一致，需要人工核查"))
    return 0 if same else 1


def main(argv):
    for t in TOOLS:
        if shutil.which(t) is None:
            print("找不到 %s：先 export PATH=/Users/a0000/micromamba/envs/cdev/bin:$PATH" % t)
            return 2

    args = argv[1:]
    if not args:
        print(USAGE)
        return 2

    if args[0] == "--diff":
        if len(args) < 3:
            print(USAGE)
            return 2
        return diff(args[1], args[2])

    expect_fail = False
    if args[0] == "--expect-fail":
        expect_fail = True
        args = args[1:]

    rc = 0
    for elf in args:
        rc |= check(elf, expect_fail)
        print()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
