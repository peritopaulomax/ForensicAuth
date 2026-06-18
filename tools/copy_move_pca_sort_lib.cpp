// In-process std::sort for lexicographic block keys (Peritus-compatible).
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <numeric>
#include <vector>

#if defined(_WIN32)
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

extern "C" {

// Sort indices by keys[i1] < keys[i2]. keys length nb; writes indices to out (preallocated, size nb).
EXPORT void copy_move_pca_sort_indices(const double* keys, int nb, int* out) {
    std::vector<int> ind(nb);
    std::iota(ind.begin(), ind.end(), 0);
    std::sort(ind.begin(), ind.end(), [&](int i1, int i2) { return keys[i1] < keys[i2]; });
    std::memcpy(out, ind.data(), static_cast<size_t>(nb) * sizeof(int));
}

}  // extern "C"
