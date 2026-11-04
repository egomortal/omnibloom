// Verify that the static platform loader supplies a working local clipboard.
#include <wpe/wpe.h>
#include <assert.h>
#include <string.h>
#include <stdio.h>

int main()
{
    auto* clipboard = wpe_pasteboard_get_singleton();
    assert(clipboard);
    wpe_pasteboard_string_pair pair { };
    const char* type = "text/plain";
    const char* text = "Omni clipboard: caf\xc3\xa9";
    wpe_pasteboard_string_initialize(&pair.type, type, strlen(type));
    wpe_pasteboard_string_initialize(&pair.string, text, strlen(text));
    wpe_pasteboard_string_map map { &pair, 1 };
    wpe_pasteboard_write(clipboard, &map);
    wpe_pasteboard_string value { };
    wpe_pasteboard_get_string(clipboard, type, &value);
    assert(value.length == strlen(text));
    assert(!memcmp(value.data, text, value.length));
    wpe_pasteboard_string_vector types { };
    wpe_pasteboard_get_types(clipboard, &types);
    assert(types.length == 1);
    assert(types.strings[0].length == strlen(type));
    assert(!memcmp(types.strings[0].data, type, strlen(type)));
    wpe_pasteboard_string_vector_free(&types);
    wpe_pasteboard_string_free(&value);
    wpe_pasteboard_string_free(&pair.type);
    wpe_pasteboard_string_free(&pair.string);
    puts("WPE clipboard round trip passed");
}
