/* Milvus 2.5.6 bitset dispatch checks CPUID without checking OS AVX state.
 * On the affected VM this selects AVX512 even though Linux cannot use AVX.
 * Restrict bitset dispatch to the existing baseline implementation.
 * FAISS is independently restricted by user.yaml. Only use this image on
 * x86-64 hosts with SSE4.2; it trades SIMD performance for compatibility.
 */
#include <stdbool.h>

bool bitset_avx2(void) __asm__("_ZN6milvus6bitset6detail3x8616cpu_support_avx2Ev");
bool bitset_avx512(void) __asm__("_ZN6milvus6bitset6detail3x8618cpu_support_avx512Ev");

bool bitset_avx2(void) { return false; }
bool bitset_avx512(void) { return false; }
