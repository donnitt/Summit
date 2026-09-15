# Summit Desktop

Aplicativo financeiro local para vida pessoal e trabalho autônomo. O Summit funciona sem navegador, servidor, conta online ou internet. Todos os dados ficam em um banco SQLite privado no próprio computador.

## Baixar pelo GitHub

Depois que o código estiver na branch `main`, clique em **Code → Download ZIP**,
extraia o arquivo e siga a etapa abaixo para gerar o programa no Windows.

## Gerar o `.exe` no seu computador

No Windows, instale o [Python](https://www.python.org/downloads/) marcando **Add Python to PATH**. Depois extraia o projeto e dê dois cliques em:

```text
criar_executavel_windows.bat
```

Ao terminar, o programa estará em `dist\Summit.exe`. Esse executável pode ser copiado para outro computador Windows e aberto sem instalar Python.

O Windows poderá mostrar um aviso porque o executável ainda não possui certificado comercial. Nesse caso, use **Mais informações → Executar assim mesmo** somente se o arquivo veio deste repositório.

## Executar para desenvolvimento

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

## Onde os dados ficam

No Windows, o banco é salvo em:

```text
%LOCALAPPDATA%\Summit\summit.db
```

O arquivo fica fora da pasta do programa. Assim, substituir o `Summit.exe` por uma versão nova não apaga os lançamentos.

## Funcionalidades

- onboarding persistente em três etapas;
- modo demonstração voltado a profissionais autônomos;
- quadro financeiro com entradas casuais, valores a receber e gastos visíveis ao mesmo tempo;
- área exclusiva de fixos, com entradas e gastos recorrentes separados entre pessoal e trabalho;
- cartões clicáveis que abrem a edição e oferecem exclusão segura dentro da própria janela;
- classificação pessoal ou trabalho em movimentações e contas fixas;
- contas fixas separadas entre pessoal e trabalho, com subtotais, vencimento e status ativo ou pausado;
- contas editáveis, com múltiplas contas, saldo-base ajustável e saldo atual calculado;
- área de dívidas com credor, saldo devedor, parcelas, vencimentos, quitação e exclusão;
- alertas de recebimentos no dashboard, com reagendamento e confirmação de entrada em conta;
- saldo consolidado, fluxo de caixa e gastos por categoria com visão semanal, mensal ou anual;
- modo de privacidade para ocultar ou revelar todos os valores financeiros em qualquer tela;
- metas com prazo, aporte mensal e cálculo do ritmo necessário;
- limites de gastos por categoria comparados ao realizado no mês;
- carteira de investimentos com posição, custo, rentabilidade e instituição;
- relatórios por período com análise financeira e exportação em CSV;
- datas escolhidas somente por calendário visual, com navegação por dia, mês e ano;
- campos monetários que substituem o valor selecionado ao iniciar uma nova digitação;
- banco SQLite local e funcionamento offline.
