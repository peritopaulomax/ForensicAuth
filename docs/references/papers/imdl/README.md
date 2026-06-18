# Artigos PDF — técnicas IML/DL (localização de manipulação)

PDFs oficiais baixados dos repositórios e fontes open access, organizados por ID da técnica no VA Suite.

## Estrutura

```
imdl/
├── manifest.json          # metadados, URLs e caminhos locais
├── safire/paper.pdf
├── trufor/paper.pdf
├── cat_net/paper.pdf
├── objectformer/paper.pdf
├── sparse_vit/paper.pdf
├── mesorch/paper.pdf
├── dinov3_iml/paper.pdf
└── co_transformers/paper.pdf
```

## Re-download

```bash
conda activate va-suite
python scripts/download_imdl_papers.py
```

## Fontes utilizadas

| ID | Venue | Fonte do PDF |
|----|-------|----------------|
| `safire` | AAAI 2025 | [arXiv:2412.08197](https://arxiv.org/pdf/2412.08197.pdf) |
| `trufor` | CVPR 2023 | [CVF Open Access](https://openaccess.thecvf.com/content/CVPR2023/papers/Guillaro_TruFor_Leveraging_All-Round_Clues_for_Trustworthy_Image_Forgery_Detection_and_CVPR_2023_paper.pdf) |
| `cat_net` | IJCV 2022 (v2) | [arXiv:2108.12947](https://arxiv.org/pdf/2108.12947.pdf) |
| `objectformer` | CVPR 2022 | [CVF Open Access](https://openaccess.thecvf.com/content/CVPR2022/papers/Wang_ObjectFormer_for_Image_Manipulation_Detection_and_Localization_CVPR_2022_paper.pdf) |
| `sparse_vit` | AAAI 2025 | [arXiv:2412.14598](https://arxiv.org/pdf/2412.14598.pdf) |
| `mesorch` | AAAI 2025 | [arXiv:2412.13753](https://arxiv.org/pdf/2412.13753.pdf) |
| `dinov3_iml` | arXiv 2026 | [arXiv:2604.16083](https://arxiv.org/pdf/2604.16083.pdf) |
| `co_transformers` | AAAI 2026 | [AAAI OJS](https://ojs.aaai.org/index.php/AAAI/article/download/38250/42212) |

## Uso futuro

Reservado para enriquecer cards (resumo, figuras, citação expandida) ou indexação interna. Os metadados curtos continuam em `src/frontend/src/config/forensicTechniqueMeta.ts`.

## Licença

Respeite os termos de cada editor (IEEE/CVF, AAAI, Springer/arXiv) ao redistribuir ou exibir trechos na UI.
