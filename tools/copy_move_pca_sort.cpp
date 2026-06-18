// Lexicographic index sort helper — mirrors Peritus std::sort on block keys.
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <numeric>
#include <string>
#include <vector>

int main(int argc, char** argv) {
    if (argc < 3) return 1;
    std::ifstream in(argv[1], std::ios::binary);
    if (!in) return 2;
    int nb = 0;
    in.read(reinterpret_cast<char*>(&nb), sizeof(nb));
    if (nb <= 0) return 3;
    std::vector<double> keys(nb);
    in.read(reinterpret_cast<char*>(keys.data()), nb * sizeof(double));
    if (!in) return 4;

    std::vector<int> ind(nb);
    std::iota(ind.begin(), ind.end(), 0);
    std::sort(ind.begin(), ind.end(), [&](int i1, int i2) { return keys[i1] < keys[i2]; });

    std::ofstream out(argv[2], std::ios::binary);
    if (!out) return 5;
    out.write(reinterpret_cast<const char*>(&nb), sizeof(nb));
    out.write(reinterpret_cast<const char*>(ind.data()), nb * sizeof(int));
    return 0;
}
