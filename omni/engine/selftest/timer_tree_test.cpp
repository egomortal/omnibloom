// Exercise the actual upstream checked-pointer tree used by generic run-loop timers.
// SPDX-License-Identifier: GPL-3.0-or-later
#include "config.h"
#include <WebKit/WKRunLoop.h>
#include <wtf/RedBlackTree.h>
#include <wtf/TZoneMallocInlines.h>
#include <algorithm>
#include <array>
#include <cstdio>
#include <random>

namespace {
class TestNode final : public WTF::RedBlackTree<TestNode, int>::ThreadSafeNode {
    WTF_MAKE_TZONE_ALLOCATED_INLINE(TestNode);
    WTF_OVERRIDE_DELETE_FOR_CHECKED_PTR(TestNode);
public:
    explicit TestNode(int value) : value(value) { }
    int key() const { return value; }
private:
    int value;
};
}

int omniTimerTreeSelfTest()
{
    WKRunLoopInitializeMain();
    WTF::RedBlackTree<TestNode, int> tree;
    auto* retired = new TestNode(2);
    auto* child = new TestNode(1);
    tree.insert(retired); tree.insert(child);
    tree.remove(retired);
    // Only the live tree root should still reference child. The removed parent
    // must not keep its former child alive as a checked-but-non-owning pointer.
    if (child->checkedPtrCount() != 1) {
        fprintf(stderr, "TIMER TREE FAIL: removed node retains child link\n");
        return 1; // Do not intentionally dereference a dead node on failure.
    }
    tree.remove(child);
    delete child;
    tree.insert(retired); tree.remove(retired); delete retired;

    std::mt19937 random(0x4f4d4e49);
    for (unsigned round = 0; round < 100; ++round) {
        std::array<int, 31> order;
        std::array<TestNode*, 31> nodes;
        for (int i = 0; i < 31; ++i) { order[i] = i; nodes[i] = new TestNode(i); }
        std::shuffle(order.begin(), order.end(), random);
        for (int i : order) tree.insert(nodes[i]);
        std::shuffle(order.begin(), order.end(), random);
        for (int i : order) {
            if (tree.findExact(i) != nodes[i]) return 2;
            tree.remove(nodes[i]);
            if (nodes[i]->checkedPtrCount()) {
                fprintf(stderr, "TIMER TREE FAIL: dangling incoming link round=%u key=%d\n", round, i);
                return 3;
            }
            delete nodes[i];
            if (tree.findExact(i)) return 4;
        }
    }
    fprintf(stderr, "TIMER TREE PASS: remove/destroy/reinsert and 100 randomized 31-node rounds\n");
    return 0;
}
