# Metro Mondego System

Projeto de Bases de Dados — Ano Letivo 2025/2026

## Sobre o projeto

O **Metro Mondego System** é uma REST API para gestão de um sistema de metro: autenticação e registo de utilizadores (clientes, administradores e super administrador), consulta de linhas e horários, compra e validação de bilhetes/passes, carregamento de carteira digital, gestão de tarifas e operação de linhas, e relatórios analíticos para administração (procura por horário, top clientes por linha, faturação mensal).

O projeto foi desenvolvido em torno de um modelo relacional em PostgreSQL, com particular cuidado em garantir consistência sob concorrência (transações, locks explícitos e triggers) — por exemplo, para impedir overbooking de lugares numa viagem, saldo negativo na carteira, ou validação duplicada do mesmo bilhete.

## Tecnologias utilizadas

- **Python 3.10+** — linguagem principal do backend
- **Flask** — framework da REST API
- **Flask-JWT-Extended** — autenticação e autorização baseadas em JWT (com controlo de acesso por role: `customer`, `admin`, `superadmin`)
- **PostgreSQL 14+** — base de dados relacional
- **psycopg2** — driver de acesso à base de dados
- **python-dotenv** — carregamento de configuração/segredos a partir de variáveis de ambiente
- **Postman** — coleção de testes dos endpoints (`metro_mondego.postman_collection.json`)

## Estrutura do projeto

```
.
├── src/
│   ├── rest_api.py            # Ponto de entrada; define rotas e permissões de cada endpoint
│   ├── authentication.py      # Autenticação e registo de utilizadores
│   ├── admin_endpoints.py     # Endpoints de administração (tarifas, operação de linhas, avisos, promoções)
│   ├── customer_endpoints.py  # Endpoints do cliente (carteira, compra e uso de bilhetes, avisos)
│   ├── report_endpoints.py    # Relatórios analíticos (admin/superadmin)
│   ├── global_functions.py    # Configuração da BD, setup/seed, funções auxiliares e de segurança
│   ├── hashing.py             # Hashing e verificação de passwords (PBKDF2-HMAC-SHA256)
│   └── config.py              # Configuração da aplicação Flask/JWT
├── queries/
│   ├── create_tables.sql
│   ├── create_triggers.sql
│   ├── seed_data.sql
│   └── drop_tables.sql
├── metro_mondego.postman_collection.json
├── ER FINAL.json / ER_final.png / ER_final_físico.png
├── Relatório Final BD.pdf      # Relatório completo (decisões de arquitetura, modelo de dados, etc.)
├── requirements.txt
├── .env.example
└── .gitignore
```

## Pré-requisitos

- Python 3.10 ou superior
- PostgreSQL 14 ou superior
- Postman 

## Como correr o projeto

### 1. Configurar variáveis de ambiente

Copia o ficheiro de exemplo e preenche com os teus valores:

```bash
cp .env.example .env
```

Edita o `.env` e define:

```
DB_USER=metro_admin
DB_PASSWORD=<a tua password>
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=metro_db
JWT_SECRET_KEY=<gera um valor aleatório, ver abaixo>
```

Para gerar uma `JWT_SECRET_KEY` segura:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 2. Criar a base de dados e o utilizador no PostgreSQL

```sql
CREATE USER metro_admin WITH PASSWORD '<a mesma password definida no .env>';
CREATE DATABASE metro_db OWNER metro_admin;
```

### 3. Instalar as dependências

Na diretoria raiz do projeto:

```bash
pip install -r requirements.txt
```

### 4. Correr a API

Para correr o servidor com uma base de dados nova (faz drop e recriação de tabelas, triggers e dados de teste):

```bash
python src/rest_api.py --setup
```

Para correr sem reiniciar a base de dados (em execuções seguintes):

```bash
python src/rest_api.py
```

A API fica disponível em **http://127.0.0.1:8080**.

### 5. Testar com o Postman

Importar a coleção `metro_mondego.postman_collection.json` no Postman (`File → Import`). A coleção já contém todos os endpoints configurados, com exemplos de request body.

## Endpoints principais

| Endpoint | Método | Acesso |
|---|---|---|
| `/dbproj/user` | PUT | Autenticação (login) |
| `/dbproj/register/admin` | PUT | Super Admin |
| `/dbproj/register/customer` | POST | Admin / Super Admin |
| `/dbproj/line_operation/{line_id}` | PUT | Admin / Super Admin |
| `/dbproj/fares/{fare_id}` | PUT | Admin / Super Admin |
| `/dbproj/notices/broadcast` | POST | Admin / Super Admin |
| `/dbproj/promotions` | POST | Admin / Super Admin |
| `/dbproj/lines_next` | GET | Customer |
| `/dbproj/wallet/topup` | POST | Customer |
| `/dbproj/purchase` | POST | Customer |
| `/dbproj/ticket/use/{ticket_id}` | POST | Customer |
| `/dbproj/notices` | GET | Customer |
| `/dbproj/report/demand` | GET | Admin / Super Admin |
| `/dbproj/report/top_spenders` | GET | Admin / Super Admin |
| `/dbproj/report/monthly` | GET | Admin / Super Admin |

Descrição detalhada de cada endpoint, exemplos de request/response e as decisões de arquitetura (modelo de dados, tratamento de transações e concorrência, autenticação e performance) encontram-se no **`Relatório Final BD.pdf`**.

## Segurança

- Passwords guardadas com **PBKDF2-HMAC-SHA256** (salt aleatório de 32 bytes por utilizador, 100 000 iterações).
- Autenticação e autorização via **JWT**, com verificação de role em cada endpoint protegido.
- Credenciais da base de dados e chave secreta do JWT carregadas exclusivamente a partir de variáveis de ambiente (`.env`).

## Autor

Diogo Lemos 
