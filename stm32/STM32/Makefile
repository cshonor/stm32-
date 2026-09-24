# =============================================================================
# stm32/STM32/Makefile
#
# 这份 Makefile 只写「我的工程」，其余全部交给 libopencm3 自己的 mk/ 模块。
# 契约来自 libopencm3/mk/README（官方原文）：
#   <module>-config.mk  放在「定义变量」的位置（文件上半部分）
#   <module>-rules.mk   放在「定义规则」的位置（文件下半部分）
#
# ⚠ 网上流传的模板（含很多 2020 年前的博客）里这两行现在是错的：
#     LDSCRIPT = $(OPENCM3_DIR)/lib/stm32/f1/stm32f103rb.ld
#     include  $(OPENCM3_DIR)/lib/libopencm3.rules.mk
#   实测（libopencm3 2da12dc9, 2026-07）：
#     · lib/stm32/f1/ 下没有 .ld，链接脚本由 genlink.py 依据 ld/devices.data 现场生成
#     · lib/ 下没有 libopencm3.rules.mk，构建支持已迁到 mk/ 目录
#   现在正确的做法是「只声明 DEVICE=stm32f103rb」，其余让 genlink 推导。
# =============================================================================

# ⚠ 下面几个赋值一律「注释单独占行」，不要写在赋值行尾。
#   GNU make 会把「# 之前的空白」并进变量值：实测（GNU make 4.4.1）写成
#       OPENCM3_DIR = $(CURDIR)/../../third_party/libopencm3       # 说明
#   变量值尾部会带上 7 个空格，于是 include $(OPENCM3_DIR)/mk/genlink-config.mk
#   被拆成两个文件名（.../libopencm3 与 /mk/genlink-config.mk），报出一句
#   指向完全无关位置的错：
#       make: *** .../third_party/libopencm3: Is a directory.  Stop.
#   DEVICE 带空格更隐蔽：生成出来的链接脚本会叫 "generated.stm32f103rb   .ld"。
BINARY      = blink
# 芯片型号 —— genlink 的唯一输入。
# 默认按 NUCLEO-F103RB（128K Flash / 20K RAM）；
# 手里若是 Blue Pill（STM32F103C8T6，64K / 20K），命令行覆盖即可：
#     make DEVICE=stm32f103c8        （同时把 main.c 里的 LED 从 PA5 换成 PC13）
DEVICE      ?= stm32f103rb
# 库源码位置（git 子模块，见仓库根 .gitmodules）
OPENCM3_DIR = $(CURDIR)/../../third_party/libopencm3

# 库本身要编哪个家族。注意这两个变量是两回事：
#   OPENCM3_TARGET = 编「库」时选哪些家族（make TARGETS=...，路径形式）
#   DEVICE         = 编「我的程序」时选哪颗芯片（genlink 据此生成 ld 与宏）
# F103RB 属于 stm32/f1 → 库产物是 lib/libopencm3_stm32f1.a
OPENCM3_TARGET = stm32/f1

# -----------------------------------------------------------------------------
# 工具链定位
#   macOS（本机）：官方 GNU ARM 工具链装在 ~/.local 下，没有 apt 可用
#   Linux / WSL  ：sudo apt install gcc-arm-none-eabi 之后，工具就在 PATH 上
# 两种情形都能跑：找到完整路径就用完整路径，否则退回 PATH 上的 arm-none-eabi-
# -----------------------------------------------------------------------------
TOOLCHAIN ?= $(HOME)/.local/arm-gnu-toolchain-14.2.rel1-darwin-arm64-arm-none-eabi/bin
ifeq ($(wildcard $(TOOLCHAIN)/arm-none-eabi-gcc),)
  PREFIX ?= arm-none-eabi
else
  PREFIX ?= $(TOOLCHAIN)/arm-none-eabi
endif

OBJS     += main.o
CFLAGS   += -Os -ggdb3 -Wall -Wextra
CPPFLAGS += -MD
LDFLAGS  += -static -nostartfiles -Wl,-Map=$(BINARY).map
LDLIBS   += -Wl,--start-group -lc -lgcc -lnosys -Wl,--end-group

# openocd（烧录/调试）。xpack 的 darwin-arm64 构建装在 ~/.local 下。
OPENOCD     ?= $(HOME)/.local/xpack-openocd-0.12.0-7/bin/openocd
OCD_SCRIPTS ?= $(HOME)/.local/xpack-openocd-0.12.0-7/openocd/scripts

# =============================================================================
# 变量区结束 → 引入库的 config 模块（它们会追加 CPPFLAGS/ARCH_FLAGS/LDFLAGS/LDLIBS）
# =============================================================================
# -----------------------------------------------------------------------------
# 自举：库必须先编出来，而且必须赶在 include genlink-config.mk *之前* 编好。
#
# 为什么顺序这么讲究（genlink-config.mk 第 59-70 行的原文逻辑）：
#     ifneq (,$(wildcard $(OPENCM3_DIR)/lib/libopencm3_$(genlink_family).a))
#         LIBNAME = opencm3_$(genlink_family)      ← 库在，才推得出 -lopencm3_stm32f1
#     ...
#     否则 $(warning ... library variant for the selected device does not exist)
# 也就是说 LIBNAME / LDLIBS 是「看文件在不在」推导出来的。库不在时，链接行里的
# -lopencm3_stm32f1 会整个消失，最后死在：
#     make: *** No rule to make target 'blink.elf', needed by 'all'.  Stop.
# 这句错误里没有一个字提到「库没编」，所以这里做一次自举，一次 make 就能跑通。
# -----------------------------------------------------------------------------
ifeq ($(wildcard $(OPENCM3_DIR)/lib/libopencm3_stm32f1.a),)
$(info [1/2] 库还没编 → 先构建 $(OPENCM3_TARGET)（只在第一次需要）)
$(shell $(MAKE) -C $(OPENCM3_DIR) TARGETS=$(OPENCM3_TARGET) 1>&2)
$(info [2/2] 库就绪，继续构建应用)
endif

include $(OPENCM3_DIR)/mk/genlink-config.mk
include $(OPENCM3_DIR)/mk/gcc-config.mk

# ⚠ 必须放在 genlink-config.mk 之后：
#   它用「:=」赋值 ARCH_FLAGS，写在前面的追加会被覆盖掉。
#
# -mfix-cortex-m3-ldrd：STM32F1 是 Cortex-M3 r1p1，有两处 erratum（463763/463764）会让
# 某些 64 位 ldrd 序列在跨字边界时读到错的数据。GCC 的这个开关会把不安全序列拆开。
# 官方 F1 例程的 Makefile.include 里也有这一条，容易漏。
ARCH_FLAGS += -mfix-cortex-m3-ldrd

# =============================================================================
# 我的目标
# =============================================================================
.PHONY: all clean size vectors dump flash openocd gdb lib clean-all

all: $(BINARY).elf $(BINARY).bin $(BINARY).hex

# 单独编库（第一次也可以直接 make，会自动触发这条规则，见文件末尾）
lib:
	$(MAKE) -C $(OPENCM3_DIR) TARGETS=$(OPENCM3_TARGET)

# 体积账单，用来和 stm32/01 手写版对比
size: $(BINARY).elf
	$(SIZE) $(BINARY).elf
	@echo "--- 各段明细 ---"
	$(SIZE) -A $(BINARY).elf | sed -n '2,12p'

# 向量表断言：上电瞬间硬件只读两个字段（MSP / PC），这两项错了不会有任何编译期提示
vectors: $(BINARY).elf
	python3 check_vectors.py $(BINARY).elf

# 反汇编 + 源码交错，肉眼看 main 编成了什么
dump: $(BINARY).elf
	$(OBJDUMP) -d -S $(BINARY).elf | sed -n '/<main>:/,/^$$/p'

# -----------------------------------------------------------------------------
# 烧录与调试（需要真的插上板子；没有板子时这几条会报错，属正常）
#   flash  ：一次性「编程 → 校验 → 复位 → 退出」
#   openocd：前台常驻，留出 :3333 GDB 端口
#   gdb    ：连上后在 reset_handler 处停下（比在 main 停下更有用：能看到启动序列）
# -----------------------------------------------------------------------------
flash: $(BINARY).elf
	$(OPENOCD) -s $(OCD_SCRIPTS) -f openocd/f103rb.cfg \
		-c "program $(BINARY).elf verify reset exit"

openocd:
	$(OPENOCD) -s $(OCD_SCRIPTS) -f openocd/f103rb.cfg

gdb: $(BINARY).elf
	$(PREFIX)-gdb $(BINARY).elf \
		-ex "target extended-remote :3333" \
		-ex "monitor reset halt" \
		-ex "break reset_handler" \
		-ex "continue"

clean:
	$(RM) -f $(BINARY).elf $(BINARY).bin $(BINARY).hex $(BINARY).map
	$(RM) -f *.o *.d
	$(RM) -f generated.*.ld

# 连子模块里的编译产物一起清（重新体验一次完整的构建链路时用）
clean-all:
	$(MAKE) -C $(OPENCM3_DIR) clean

# =============================================================================
# 规则区 → 引入库的 rules 模块（%.elf / %.bin / %.hex / %.o 的生成规则在这里）
# =============================================================================
# genlink-rules.mk：用 genlink.py 生成 $(DEVICE).ld
# gcc-rules.mk   ：%.elf / %.bin / %.hex / %.o 的生成规则
include $(OPENCM3_DIR)/mk/genlink-rules.mk
include $(OPENCM3_DIR)/mk/gcc-rules.mk

# 注意：这里没有、也不能有「.a 的生成规则」。
#   genlink-config.mk 把 $(OPENCM3_DIR)/lib/libopencm3_$(genlink_family).a 加进
#   LIBDEPS 的前提，是那个文件已经存在（见文件上半部分的自举块）。文件不在，
#   LIBDEPS 里放的是 lib$(LIBNAME).a（LIBNAME 为空）→ 规则永远不会被用到。
#   所以「库怎么编出来」这件事只能放在 include 之前做，不能放在规则区。
