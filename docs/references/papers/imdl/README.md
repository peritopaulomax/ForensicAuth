# Artigos PDF — técnicas de imagem

PDFs de referência das técnicas de análise de imagem, organizados por ID da técnica no ForensicAuth.

## Estrutura

```
imdl/
├── manifest.json          # metadados, URLs e caminhos locais
├── jpeg_ghosts/*.pdf
├── dct_quantization/*.pdf
├── double_compression/*.pdf
├── bag_extraction/*.pdf
├── zero_grid/*.pdf
├── resampling/*.pdf
├── patchmatch/*.pdf
├── copy_move_pca/*.pdf
├── wavelet_noise_residue/*.pdf
├── prnu/*.pdf
├── noiseprint/*.pdf
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
conda activate forensicauth
python scripts/download_imdl_papers.py
```

## Fontes utilizadas

| ID | Venue | Fonte do PDF |
|----|-------|----------------|
| `jpeg_ghosts` / `ela` | TIFS 2009 | Farid, JPEG Ghosts |
| `dct_quantization` | ICME 2007 | Ye, Sun & Chang |
| `double_compression` | IH 2004 / ICDP 2009 | Popescu & Farid; Mahdian & Saic |
| `bag_extraction` | BAG | Li, Yuan & Yu |
| `zero_grid` | IPOL 2021 | Nikoukhah et al. |
| `resampling` | TIFS 2008 | Mahdian & Saic |
| `patchmatch` | TIFS 2015 | Cozzolino, Poggi & Verdoliva |
| `copy_move_pca` | TR 2004 | Popescu & Farid |
| `wavelet_noise_residue` | IVC 2009 | Mahdian & Saic |
| `prnu` | Sensor noise / SPIE | Fridrich; Goljan et al.; Goljan & Fridrich |
| `noiseprint` | TIFS 2020 | Cozzolino & Verdoliva |
| `safire` | AAAI 2025 | [arXiv:2412.08197](https://arxiv.org/pdf/2412.08197.pdf) |
| `trufor` | CVPR 2023 | [CVF Open Access](https://openaccess.thecvf.com/content/CVPR2023/papers/Guillaro_TruFor_Leveraging_All-Round_Clues_for_Trustworthy_Image_Forgery_Detection_and_CVPR_2023_paper.pdf) |
| `cat_net` | IJCV 2022 (v2) | [arXiv:2108.12947](https://arxiv.org/pdf/2108.12947.pdf) |
| `objectformer` | CVPR 2022 | [CVF Open Access](https://openaccess.thecvf.com/content/CVPR2022/papers/Wang_ObjectFormer_for_Image_Manipulation_Detection_and_Localization_CVPR_2022_paper.pdf) |
| `sparse_vit` | AAAI 2025 | [arXiv:2412.14598](https://arxiv.org/pdf/2412.14598.pdf) |
| `mesorch` | AAAI 2025 | [arXiv:2412.13753](https://arxiv.org/pdf/2412.13753.pdf) |
| `dinov3_iml` | arXiv 2026 | [arXiv:2604.16083](https://arxiv.org/pdf/2604.16083.pdf) |
| `co_transformers` | AAAI 2026 | [AAAI OJS](https://ojs.aaai.org/index.php/AAAI/article/download/38250/42212) |

## Uso futuro

Os metadados curtos continuam em `src/frontend/src/config/forensicTechniqueMeta.ts`. O frontend consulta `manifest.json` e habilita o download quando o PDF local existe.

## Licença

Respeite os termos de cada editor (IEEE/CVF, AAAI, Springer/arXiv) ao redistribuir ou exibir trechos na UI.
