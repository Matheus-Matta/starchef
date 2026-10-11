# Lib embutida na imagem

A Action `.github/workflows/fiscal_acbr.yml` baixa aqui a `libacbrnfe64.so`
quando o Secret `ACBRLIB_SO_URL` existe, e o Dockerfile copia esta pasta para
`/opt/acbr` dentro da imagem. A `.so` nunca é versionada (`.gitignore`): tem
licença própria do Projeto ACBr. Ver `docs/FISCAL_ACBRLIB.md`.
