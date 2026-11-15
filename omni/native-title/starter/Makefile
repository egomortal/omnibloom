# Omni engine starter (OMNI_STARTER_V1). GPL-3.0-or-later; gpl/ is John Törnblom's ps5-payload-elfldr code (GPL-3.0+).
SDK ?= /opt/ps5-payload-sdk
CC := $(SDK)/bin/prospero-clang
CFLAGS := -O2 -Wall -Wextra -D__PS5__ -I$(SDK)/target/user/homebrew/include -I.
SOURCES := main.c gpl/elfldr.c gpl/pt.c
LDLIBS := -lkernel_sys

all: build/omni-starter.elf

build/omni-starter.elf: $(SOURCES) gpl/elfldr.h gpl/pt.h
	mkdir -p build
	$(CC) $(CFLAGS) -o $@ $(SOURCES) $(LDLIBS)

clean:
	rm -rf build

.PHONY: all clean
