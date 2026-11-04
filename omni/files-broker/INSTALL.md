# Installing / testing OMNI_FILES_BROKER_V1 (console)
Under the lock (`console-lock.py acquire omni-files1`), wait-console-idle (4-minute settle), never kill the title.
1. `python3 ../omni-native-s1b/run_files_test.py install` — keeps the current eboot as eboot.bin.s0b (refuses if that name exists), uploads s1b eboot + icon, uploads dist/omni-files.elf to /data/omni/native/omni-files.elf, sets /data/omni/native/files-selftest.flag.
2. Plug in a USB drive (FAT32/exFAT) with at least one file ≤ 64 MB in its top folder for the copy check.
3. `python3 ../omni-native-s1b/run_files_test.py launch` then `... logs` — look for `FILES SELFTEST PASS` in console-run-1-files/title-last.log and `title <pid> gone: exiting` in omni-files.log.
4. `python3 ../omni-native-s1b/run_files_test.py restore` — removes the flag, puts the previous eboot back, keeps s1b as eboot.bin.s1b.
Back out entirely: the broker only runs when s1b starts it; deleting /data/omni/native/omni-files.elf disables it.
