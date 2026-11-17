# Banco relacional (PostgreSQL no Cloud SQL)

**Decisão do grupo (17/11/2026):** banco relacional = PostgreSQL (Cloud SQL). **Responsável pela carga dos CSV limpos: Integrante 3.**

## O que está pronto
- `db/01_esquema.sql`: 7 tabelas de dados e a tabela `pedidos` (vazia, para a triagem registrar pedidos), com chaves primárias, chaves estrangeiras e uma checagem de status de pagamento.
- `db/02_dados.sql`: os dados limpos, em `INSERT`. **Não há CPF, PIX, conta, telefone nem e-mail** (um teste confere isso).
- `sabor/banco.py`: gera os dois arquivos a partir dos CSV limpos e, se quiser, carrega no banco.
- `tests/test_banco.py`: 8 testes (contagens iguais aos CSV, totais conhecidos, chave estrangeira, ausência de dado pessoal).

| Tabela | Linhas | Conteúdo |
|---|---|---|
| `produtores` | 18 | cadastro público (sem CPF, PIX, conta, telefone, endereço) |
| `produtores_produtos` | 64 | produtos de cada produtor |
| `restricoes_produtor` | 18 | SIE, DAP/CAF e restrições de venda, com a fonte |
| `dim_produto` | 50 | nomes padronizados e unidade |
| `tabela_precos` | 53 | preços, descontos e grade |
| `financeiro` | 30 | vendas e pagamentos |
| `lotes` | 20 | rastreabilidade |
| `pedidos` | 0 | vazia, para a triagem (proposta; ajustar com quem faz a triagem) |

## Como carregar no Cloud SQL (quem tiver a instância)
Os arquivos funcionam em qualquer PostgreSQL. Há três caminhos; escolha o mais fácil.

**A. Cloud SQL Studio (sem instalar nada).** No console do Google Cloud, abra a instância, vá em *Cloud SQL Studio*, entre no banco e rode primeiro o conteúdo de `db/01_esquema.sql` e depois o de `db/02_dados.sql`.

**B. psql pelo Cloud SQL Auth Proxy.** Em um terminal, abra o proxy e, em outro, carregue:
```
cloud-sql-proxy PROJETO:REGIAO:INSTANCIA --port 5432
psql "host=127.0.0.1 port=5432 dbname=BANCO user=USUARIO" -f db/01_esquema.sql
psql "host=127.0.0.1 port=5432 dbname=BANCO user=USUARIO" -f db/02_dados.sql
```
A senha é pedida no terminal ou vem de `PGPASSWORD`. **Nunca** colocar a senha em arquivo do repositório.

**C. Python.** `py -m pip install "psycopg[binary]"` e depois `py -m sabor.banco --dsn "postgresql://USUARIO@127.0.0.1:5432/BANCO"` (com o proxy aberto e `PGPASSWORD` definida).

A carga pode ser repetida: o esquema apaga e recria as tabelas, e os dados entram de novo. Depois da carga, o `pedidos` só terá linhas quando a triagem gravar.

## Para recriar os arquivos SQL
```
py -m sabor.limpeza
py -m sabor.banco --gerar-sql
```

## Como foi testado e o que falta
- **Testado:** o esquema e os dados foram carregados em um PostgreSQL 16 local, duas vezes seguidas (recarga ok). As contagens batem com os CSV, e as consultas conferem com a análise: R$ 13.380 pendentes (R$ 10.500 vencidos em 14/11) e R$ 6.020 da SuperBom. A chave estrangeira rejeita produtor inexistente. Os 8 testes automáticos rodam em SQLite, sem rede.
- **Não testado:** a carga em uma instância **Cloud SQL** real (depende de acesso do Isaque) e o caminho `--dsn` com o `psycopg`.
- **Falta (próximo passo):** as ferramentas `consultar_lote`, `situacao_produtor` e `extrato_produtor` ainda leem dos CSV limpos. Quando o banco estiver no ar, trocar a leitura para o PostgreSQL é uma mudança pequena, porque todas passam por uma única função (`_tabela` em `sabor/dados.py`). A conexão e a senha ficam no Secret Manager.
- Os dados do banco são os mesmos dos CSV: mudou o lugar, e não o conteúdo.
