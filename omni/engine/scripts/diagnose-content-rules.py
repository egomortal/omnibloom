"""Temporary stage logging for the PlayStation content-rule compiler."""
import pathlib
import sys
p = pathlib.Path(sys.argv[1]) / 'Source/WebKit/UIProcess/API/APIContentRuleListStore.cpp'
s = p.read_text()
if '[omni-rule-diagnostics]' not in s:
    s = '#include <cstdio> // [omni-rule-diagnostics]\n' + s
    for anchor, label in [
        ('    auto sharedMemory = data.data.tryCreateSharedMemory();', 'creating shared memory'),
        ('    RELEASE_ASSERT(sharedMemory);', 'shared memory returned'),
        ('    auto [temporaryFilePath, temporaryFileHandle] = openTemporaryFile', 'opening temporary file'),
        ('    if (auto compilerError = compileRuleList', 'compiling bytecode'),
        ('    auto mappedData = mapFile(finalFilePath);', 'mapping compiled file'),
        ('        auto result = compiledToFile', 'worker started'),
        ('        if (!result.has_value()) {', 'worker compiled'),
    ]:
        assert anchor in s, anchor
        s = s.replace(anchor, '    fprintf(stderr, "rules: ' + label + '\\n"); fflush(stderr);\n' + anchor, 1)
    p.write_text(s)
if 'rules: compiler error' not in s:
    s = s.replace('        if (!result.has_value()) {', '        if (!result.has_value()) {\n            fprintf(stderr, "rules: compiler error %d %s\\n", result.error().value(), result.error().message().c_str()); fflush(stderr);', 1)
    p.write_text(s)
