# pdfsig_forense.py

Análise forense de assinaturas digitais em PDF (PAdES/CAdES), com ênfase em
ICP-Brasil, produzindo um **relatório humanizado em Markdown** — não apenas um
"válido/inválido".

## Instalação

```bash
pip install pyhanko asn1crypto cryptography
```

Python 3.9+. Funciona **offline** por padrão: nenhuma consulta de rede.

## Uso

```bash
# análise completa no terminal
python3 pdfsig_forense.py documento.pdf

# relatório em arquivo, com hora local de Brasília ao lado do UTC
python3 pdfsig_forense.py documento.pdf --tz -3 -o relatorio.md

# ancorando a validação na raiz OFICIAL (recomendado)
python3 pdfsig_forense.py documento.pdf --trust-anchor raiz-icpbrasil-v5.crt -o relatorio.md

# dados brutos para automação/planilha
python3 pdfsig_forense.py documento.pdf --json dados.json

# extrair todos os certificados e LCRs encontrados (inclusive órfãos)
python3 pdfsig_forense.py documento.pdf --dump-material ./material

# exibir CPF/RG do responsável (ocultados por padrão)
python3 pdfsig_forense.py documento.pdf --no-redact
```

**Código de saída:** `0` sem achados críticos · `1` com achado crítico ·
`2` arquivo não encontrado · `3` erro de processamento. Serve para uso em
pipelines e triagem em lote.

### Triagem em lote

```bash
for f in *.pdf; do
  python3 pdfsig_forense.py "$f" --quiet -o "relatorios/${f%.pdf}.md" \
    || echo "PROBLEMA CRÍTICO: $f"
done
```

## O que o script verifica

**Integridade e autoria**
- Recalcula o digest do `/ByteRange` e compara com o `messageDigest` do CMS
- Verifica a assinatura RSA (PKCS#1 v1.5 e PSS), ECDSA ou DSA com a chave pública
- Detecta lacunas de cobertura: bytes não assinados *dentro* do trecho coberto,
  além do espaço reservado à própria assinatura (fraude clássica)
- Distingue bytes acrescentados em revisão legítima de lixo anexado ao fim
- Confere o atributo `signingCertificate(V2)` (ESS): cardinalidade e hash

**Certificados e cadeia**
- Verifica cada vínculo da cadeia, um a um, matematicamente
- Monta a cadeia usando **todo** o material do arquivo, inclusive objetos
  órfãos desreferenciados por revisões posteriores (que validadores ignoram)
- Valida o caminho em três cenários: no instante do carimbo com revogação
  obrigatória, tolerando falta de revogação, e na data de hoje
- Lê os campos ICP-Brasil (`2.16.76.1.3.x`: CNPJ, responsável, dados pessoais)
  e as políticas de certificado (A1/A2/A3/A4, sigilo, carimbo do tempo)
- Sinaliza chave curta, hash frágil, `keyUsage` sem `nonRepudiation`, ausência
  de responder OCSP

**Carimbos de tempo**
- Extrai `signature-time-stamp`, `content-time-stamp` e `/DocTimeStamp`
- Confere se o `messageImprint` realmente corresponde ao alvo (impede carimbo
  "emprestado" de outro documento)
- Verifica a assinatura do token, o EKU exclusivo `timeStamping` da ACT e a
  cadeia da autoridade de carimbo
- Lê a **Declaração de Sincronismo** da Entidade de Auditoria do Tempo
  (extensão proprietária ICP-Brasil dentro do TSTInfo)

**Revogação e longo prazo**
- Localiza LCRs e respostas OCSP no DSS, no VRI, no CMS e no atributo
  `adbe-revocationInfoArchival`
- Verifica se o número de série consta como revogado, e se a LCR estava vigente
  no instante da assinatura
- Analisa a estrutura `/DSS` e `/VRI`, e rastreia sua **evolução por revisão** —
  detecta, por exemplo, cadeia gravada e depois desreferenciada
- Determina o nível PAdES atingido: B-B, B-T, B-LT, B-LTA (e "incompleto")
- Verifica se o material de LTV está selado por carimbo de documento

**Revisões incrementais**
- Lista o que cada revisão gravou, objeto por objeto
- Compara `/Info` e XMP entre a revisão assinada e a final
- Classifica as diferenças (nenhuma / LTV / formulário / anotações / suspeitas)
- Detecta DocMDP, FieldMDP, `/Perms`, campos de assinatura vazios

## Estrutura do relatório gerado

1. Veredito resumido (tabela + narrativa)
2. Estrutura do documento
3. Uma seção por assinatura: estrutura, integridade, certificado, cadeia,
   revogação, carimbos, validação de caminho
4. Material de validação de longo prazo (DSS/VRI)
5. Revisões incrementais
6. Material criptográfico encontrado (com origem de cada item)
7. Achados classificados: CRÍTICO / ALERTA / ATENÇÃO / OK / INFO
8. O que a assinatura prova — e o que não prova
9. Recomendações práticas, geradas conforme os achados

## Limites

- **Não julga a confiança da âncora.** Sem `--trust-anchor`, usa raízes
  autoassinadas do próprio arquivo e avisa da circularidade. Compare sempre os
  fingerprints com os publicados oficialmente (ITI, no caso da ICP-Brasil).
- **Não substitui o validador oficial** (`validar.iti.gov.br`) para fins
  formais, nem perícia quando há achado crítico.
- **Não avalia o mérito do conteúdo.** Assinatura prova integridade, origem e
  data — não veracidade.
- A classificação de severidade é heurística de auxílio, não parecer jurídico.
- Certificados de atributo, assinaturas de longo prazo com carimbos em cascata e
  perfis exóticos são reportados, mas não recebem tratamento especializado.

## Nota técnica

A comparação entre revisões usa um leitor recém-aberto e exclusivo. O pyHanko
percorre as revisões históricas em busca de objetos órfãos e falha se o mesmo
leitor já tiver sido usado para outras leituras — os objetos ficam em cache numa
forma que perde a referência ao contêiner original. Foi o bug mais difícil de
achar na construção deste script; se você adaptar o código, preserve essa
separação de leitores.
