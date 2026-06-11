# Corretor Inteligente de Textos

Aplicativo Streamlit para revisao de textos de livros e transcricoes.

## Funcionalidades

- **Regras Mecanicas**: Espacamento, pontuacao, maiusculas, aspas, travessoes
- **LanguageTool**: Ortografia, crase, concordancia, regencia verbal
- **Deteccao de OCR**: Numeros no meio de palavras, caracteres suspeitos
- **Visualizacao**: Texto original vs corrigido lado a lado
- **Destaques coloridos**: Cada tipo de correcao em uma cor diferente
- **Exportacao**: TXT, HTML e relatorio detalhado

## Requisitos

1. Python 3.8+
2. Java 8+ (para LanguageTool)

## Instalacao Rapida

### 1. Instalar Python

Baixe em: https://www.python.org/downloads/

### 2. Instalar Java (para LanguageTool)

Baixe em: https://www.java.com/pt-BR/download/

Ou via terminal (Windows):
```
winget install EclipseAdoptium.Temurin.17.JRE
```

### 3. Instalar dependencias Python

```bash
pip install streamlit PyPDF2 requests
```

### 4. Rodar o aplicativo

```bash
streamlit run app.py
```

O navegador abrira automaticamente em http://localhost:8501

## Como usar

1. Cole o texto na caixa de texto ou faca upload de um arquivo TXT/PDF
2. Clique em "CORRIGIR TEXTO"
3. Veja o resultado lado a lado
4. Baixe o texto corrigido, HTML com destaques ou relatorio

## Cores das Correcoes

- **Amarelo**: Regras mecanicas (espaco, pontuacao, maiusculas)
- **Vermelho**: Ortografia
- **Azul**: Crase
- **Verde**: Concordancia
- **Laranja**: OCR suspeito

Passe o mouse sobre as marcacoes coloridas para ver a explicacao!

## Primeira vez

Na primeira execucao, o app baixa automaticamente o LanguageTool (~200MB).
Isso pode levar alguns minutos dependendo da conexao.

## Solucao de problemas

### "Java nao encontrado"
Instale o Java e reinicie o computador.

### "LanguageTool nao inicia"
Verifique se a porta 8081 esta livre:
```bash
# Windows
netstat -ano | findstr 8081

# Linux/Mac
lsof -i :8081
```

### PDF nao le
Certifique-se de que o PDF tem texto selecionavel (nao e imagem escaneada).

## Dica

Para livros escaneados (imagens), use primeiro um OCR como:
- Tesseract (gratuito)
- Google Drive (upload e download como TXT)
- Adobe Acrobat (pago)

Depois cole o texto resultante no app.
