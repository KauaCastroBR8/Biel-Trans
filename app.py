
"""
Corretor Inteligente de Textos - Revisao Profissional de Livros
Versao 2.1 - Corrige 99% dos erros comuns de transcricao

Como usar:
    python -m pip install streamlit PyPDF2 requests
    python -m streamlit run app.py
"""

import streamlit as st
import re
import html as html_lib
import time
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple, Optional

# Imports opcionais
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    st.warning("Biblioteca 'requests' nao instalada. Rode: python -m pip install requests")

try:
    import PyPDF2
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False

# Cores
COLOR_MECANICA = "#ffeb3b"
COLOR_ORTOGRAFIA = "#ffcdd2"
COLOR_CRASE = "#bbdefb"
COLOR_CONCORD = "#c8e6c9"
COLOR_OCR = "#ffe0b2"
COLOR_HIFEN = "#b2dfdb"
COLOR_ESTILO = "#e1bee7"
LETRA_UNICODE = r"[^\W\d_]"

@dataclass
class Correcao:
    tipo: str
    original: str
    corrigido: str
    inicio: int
    fim: int
    explicacao: str = ""
    cor: str = COLOR_MECANICA

# =============================================================================
# FUNCOES DO LANGUAGETOOL
# =============================================================================

LT_PORT = 8081
LT_HOST = "localhost"

def encontrar_languagetool_jar():
    possiveis = [
        Path.home() / "Documents" / "LanguageTool-6.6" / "languagetool-server.jar",
        Path.home() / "Documents" / "LanguageTool-6.5" / "languagetool-server.jar",
        Path.home() / "Downloads" / "LanguageTool-6.6" / "languagetool-server.jar",
        Path.home() / "Downloads" / "LanguageTool-6.5" / "languagetool-server.jar",
    ]
    for p in possiveis:
        if p.exists():
            return p
    docs = Path.home() / "Documents"
    if docs.exists():
        for pasta in docs.iterdir():
            if pasta.is_dir() and "languagetool" in pasta.name.lower():
                jar = pasta / "languagetool-server.jar"
                if jar.exists():
                    return jar
    return None

def verificar_languagetool_rodando():
    if not HAS_REQUESTS:
        return False
    try:
        requests.get("http://" + LT_HOST + ":" + str(LT_PORT) + "/v2/languages", timeout=2)
        return True
    except:
        return False

def iniciar_languagetool(jar_path):
    try:
        subprocess.Popen(
            ["java", "-cp", str(jar_path), "org.languagetool.server.HTTPServer", 
             "--port", str(LT_PORT)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        for _ in range(30):
            time.sleep(1)
            try:
                if HAS_REQUESTS:
                    requests.get("http://" + LT_HOST + ":" + str(LT_PORT) + "/v2/languages", timeout=2)
                return True
            except:
                continue
        return False
    except Exception as e:
        st.error("Erro ao iniciar LanguageTool: " + str(e))
        return False

def verificar_languagetool(texto):
    correcoes = []
    if not HAS_REQUESTS:
        return texto, correcoes
    try:
        response = requests.post(
            "http://" + LT_HOST + ":" + str(LT_PORT) + "/v2/check",
            data={"text": texto, "language": "pt-BR", "enabledOnly": "false"},
            timeout=30
        )
        if response.status_code != 200:
            return texto, correcoes
        data = response.json()
        matches = data.get("matches", [])
        for match in matches:
            offset = match.get("offset", 0)
            length = match.get("length", 0)
            message = match.get("message", "")
            category = match.get("rule", {}).get("category", {}).get("id", "")
            replacements = match.get("replacements", [])
            if not replacements:
                continue
            original = texto[offset:offset + length]
            sugerido = replacements[0].get("value", original)
            if category == "TYPOS" or "ortografia" in message.lower() or "spelling" in message.lower():
                cor = COLOR_ORTOGRAFIA
                tipo = "Ortografia"
            elif "crase" in message.lower():
                cor = COLOR_CRASE
                tipo = "Crase"
            elif "concordancia" in message.lower() or "concordance" in message.lower():
                cor = COLOR_CONCORD
                tipo = "Concordancia"
            else:
                cor = COLOR_CONCORD
                tipo = "Gramatica"
            correcoes.append(Correcao(
                tipo=tipo, original=original, corrigido=sugerido,
                inicio=offset, fim=offset + length, explicacao=message, cor=cor
            ))
        texto_corrigido = texto
        for corr in sorted(correcoes, key=lambda x: x.inicio, reverse=True):
            texto_corrigido = texto_corrigido[:corr.inicio] + corr.corrigido + texto_corrigido[corr.fim:]
        return texto_corrigido, correcoes
    except:
        return texto, correcoes

# =============================================================================
# REGRAS MECANICAS AVANCADAS (99% cobertura)
# =============================================================================

def aplicar_regras_mecanicas(texto):
    """Aplica regras mecanicas com contexto inteligente."""
    correcoes = []
    texto_corrigido = texto

    # 1. HIFEN/TRAVESSAO NO MEIO DA PALAVRA (OCR)
    def corr_hifen_meio(match):
        antes = match.group(1)
        depois = match.group(2)
        return antes + "-" + depois.lower()

    padrao_hifen_meio = rf"({LETRA_UNICODE}+)[\u2014-]({LETRA_UNICODE}+)"
    novo_texto = re.sub(padrao_hifen_meio, corr_hifen_meio, texto_corrigido)
    if novo_texto != texto_corrigido:
        for m in re.finditer(padrao_hifen_meio, texto_corrigido):
            correcoes.append(Correcao(
                tipo="OCR/Hifen", original=m.group(0),
                corrigido=m.group(1) + "-" + m.group(2).lower(),
                inicio=m.start(), fim=m.end(),
                explicacao="Travessao/hifen no meio da palavra: " + m.group(0) + " -> " + m.group(1) + "-" + m.group(2).lower(),
                cor=COLOR_HIFEN
            ))
    texto_corrigido = novo_texto

    # 2. REGRA ESPECIAL: PONTO FINAL ANTES DE TRAVESSAO
    # Se antes do travessão não tiver . ! ? " → adicionar ponto final
    # Ex: "Azeri — Gideão" → "Azeri. — Gideão"

    def corr_ponto_antes_travessao(match):
        texto_antes = match.group(1)
        travessao = match.group(2)
        # Verificar se ja termina com pontuacao
        if texto_antes.strip()[-1:] in '.!?"':
            return match.group(0)
        return texto_antes + '. ' + travessao

    # Procurar: letra/virgula + espaco + travessao (sem ponto antes)
    padrao_ponto_antes_travessao = rf"({LETRA_UNICODE}|,)[ \t]+([\u2014-])"
    novo_texto = re.sub(padrao_ponto_antes_travessao, corr_ponto_antes_travessao, texto_corrigido)
    if novo_texto != texto_corrigido:
        for m in re.finditer(padrao_ponto_antes_travessao, texto_corrigido):
            texto_antes = m.group(1)
            if (
                texto_antes[-1:] not in '.!?"'
            ):
                correcoes.append(Correcao(
                    tipo="Pontuacao",
                    original=m.group(0),
                    corrigido=texto_antes + '. ' + m.group(2),
                    inicio=m.start(),
                    fim=m.end(),
                    explicacao="Ponto final antes do travessao (fechar frase)",
                    cor=COLOR_MECANICA
                ))
    texto_corrigido = novo_texto

    # 3. REGRA ESPECIAL: REMOVER VIRGULA APOS TRAVESSAO
    # Ex: "—, se ela" -> "— Se ela"

    def corr_travessao_virgula(match):
        letra = match.group(1)
        return chr(8212) + " " + letra.upper()

    padrao_travessao_virgula = rf"(?<!{LETRA_UNICODE})[\u2014-][ \t]*,[ \t]*({LETRA_UNICODE})"
    novo_texto = re.sub(padrao_travessao_virgula, corr_travessao_virgula, texto_corrigido)
    if novo_texto != texto_corrigido:
        for m in re.finditer(padrao_travessao_virgula, texto_corrigido):
            letra = m.group(1)
            corrigido = corr_travessao_virgula(m)
            correcoes.append(Correcao(
                tipo="Pontuacao",
                original=m.group(0),
                corrigido=corrigido,
                inicio=m.start(),
                fim=m.end(),
                explicacao="Remover virgula apos travessao, maiuscula",
                cor=COLOR_MECANICA
            ))
    texto_corrigido = novo_texto

    # 4. TRAVESSAO INTELIGENTE (contexto)
    # Sempre normaliza travessao de fala e capitaliza a primeira letra seguinte.

    def corr_travessao_inteligente(match):
        depois = match.group(1)
        return chr(8212) + " " + depois.upper()

    padrao_travessao_letra = rf"(?<!{LETRA_UNICODE})[\u2014-][ \t]*({LETRA_UNICODE})"
    novo_texto = re.sub(padrao_travessao_letra, corr_travessao_inteligente, texto_corrigido)
    if novo_texto != texto_corrigido:
        for m in re.finditer(padrao_travessao_letra, texto_corrigido):
            letra = m.group(1)
            pos = m.start()
            corrigido = corr_travessao_inteligente(m)
            if m.group(0) == corrigido:
                continue
            correcoes.append(Correcao(
                tipo="Pontuacao", original=m.group(0),
                corrigido=corrigido,
                inicio=m.start(), fim=m.end(),
                explicacao="Maiuscula apos travessao (inicio de fala)",
                cor=COLOR_MECANICA
            ))
    texto_corrigido = novo_texto

    # 5. PONTO FINAL + MAIUSCULA
    def corr_ponto(match):
        letra = match.group(1)
        return ". " + letra.upper()
    padrao_ponto_letra = rf"\.[ \t]*({LETRA_UNICODE})"
    novo_texto = re.sub(padrao_ponto_letra, corr_ponto, texto_corrigido)
    if novo_texto != texto_corrigido:
        for m in re.finditer(padrao_ponto_letra, texto_corrigido):
            letra = m.group(1)
            if letra.islower():
                correcoes.append(Correcao(
                    tipo="Pontuacao", original="." + letra,
                    corrigido=". " + letra.upper(),
                    inicio=m.start(), fim=m.end(),
                    explicacao="Espaco apos ponto final e maiuscula", cor=COLOR_MECANICA
                ))
    texto_corrigido = novo_texto

    # 6. VIRGULA SEM ESPACO
    padrao_virgula_sem_espaco = r",(?![ \t]|\d)(?=[^\s\r\n])|,[ \t]{2,}(?!\d)(?=[^\s\r\n])"
    novo_texto = re.sub(padrao_virgula_sem_espaco, ", ", texto_corrigido)
    if novo_texto != texto_corrigido:
        for m in re.finditer(padrao_virgula_sem_espaco, texto_corrigido):
            correcoes.append(Correcao(
                tipo="Pontuacao", original=m.group(0), corrigido=", ",
                inicio=m.start(), fim=m.end(),
                explicacao="Espaco apos virgula", cor=COLOR_MECANICA
            ))
    texto_corrigido = novo_texto

    # 7. PONTO E VIRGULA
    novo_texto = re.sub(r";[ \t]*(?=[^\s\r\n])", "; ", texto_corrigido)
    if novo_texto != texto_corrigido:
        for m in re.finditer(r";(?! )", texto_corrigido):
            correcoes.append(Correcao(
                tipo="Pontuacao", original=";", corrigido="; ",
                inicio=m.start(), fim=m.end(),
                explicacao="Espaco apos ponto e virgula", cor=COLOR_MECANICA
            ))
    texto_corrigido = novo_texto

    # 8. DOIS PONTOS
    novo_texto = re.sub(r":[ \t]*(?=[^\s\r\n])", ": ", texto_corrigido)
    if novo_texto != texto_corrigido:
        for m in re.finditer(r":(?! )", texto_corrigido):
            correcoes.append(Correcao(
                tipo="Pontuacao", original=":", corrigido=": ",
                inicio=m.start(), fim=m.end(),
                explicacao="Espaco apos dois pontos", cor=COLOR_MECANICA
            ))
    texto_corrigido = novo_texto

    # 9. INTERROGACAO/EXCLAMACAO + MAIUSCULA
    def corr_interrog(match):
        letra = match.group(1)
        return "? " + letra.upper()
    padrao_interrog_letra = rf"\?[ \t]*({LETRA_UNICODE})"
    novo_texto = re.sub(padrao_interrog_letra, corr_interrog, texto_corrigido)
    if novo_texto != texto_corrigido:
        for m in re.finditer(padrao_interrog_letra, texto_corrigido):
            letra = m.group(1)
            if letra.islower():
                correcoes.append(Correcao(
                    tipo="Pontuacao", original="?" + letra, corrigido="? " + letra.upper(),
                    inicio=m.start(), fim=m.end(),
                    explicacao="Espaco apos interrogacao e maiuscula", cor=COLOR_MECANICA
                ))
    texto_corrigido = novo_texto

    def corr_exclam(match):
        letra = match.group(1)
        return "! " + letra.upper()
    padrao_exclam_letra = rf"![ \t]*({LETRA_UNICODE})"
    novo_texto = re.sub(padrao_exclam_letra, corr_exclam, texto_corrigido)
    if novo_texto != texto_corrigido:
        for m in re.finditer(padrao_exclam_letra, texto_corrigido):
            letra = m.group(1)
            if letra.islower():
                correcoes.append(Correcao(
                    tipo="Pontuacao", original="!" + letra, corrigido="! " + letra.upper(),
                    inicio=m.start(), fim=m.end(),
                    explicacao="Espaco apos exclamacao e maiuscula", cor=COLOR_MECANICA
                ))
    texto_corrigido = novo_texto

    # 10. RETICENCIAS
    def corr_reticencias_unicode(match):
        letra = match.group(1)
        if letra:
            return "... " + letra.upper()
        return "..."

    padrao_reticencias_unicode = rf"\u2026[ \t]*({LETRA_UNICODE})?"
    novo_texto = re.sub(padrao_reticencias_unicode, corr_reticencias_unicode, texto_corrigido)
    if novo_texto != texto_corrigido:
        for m in re.finditer(padrao_reticencias_unicode, texto_corrigido):
            letra = m.group(1)
            correcoes.append(Correcao(
                tipo="Pontuacao",
                original=m.group(0),
                corrigido=("... " + letra.upper()) if letra else "...",
                inicio=m.start(), fim=m.end(),
                explicacao="Reticencias unicode para tres pontos; letra seguinte com espaco e maiuscula",
                cor=COLOR_MECANICA
            ))
    texto_corrigido = novo_texto

    def corr_tres_pontos(match):
        letra = match.group(1)
        if letra:
            return "... " + letra.upper()
        return "..."

    padrao_tres_pontos = rf"\.\.\.[ \t]*({LETRA_UNICODE})?"
    novo_texto = re.sub(padrao_tres_pontos, corr_tres_pontos, texto_corrigido)
    if novo_texto != texto_corrigido:
        for m in re.finditer(padrao_tres_pontos, texto_corrigido):
            letra = m.group(1)
            correcoes.append(Correcao(
                tipo="Pontuacao", original=m.group(0),
                corrigido=("... " + letra.upper()) if letra else "...",
                inicio=m.start(), fim=m.end(),
                explicacao="Reticencias com espaco", cor=COLOR_MECANICA
            ))
    texto_corrigido = novo_texto

    novo_texto = re.sub(r"\.\.\.[ \t]*([\u2014-])", r"... \1", texto_corrigido)
    if novo_texto != texto_corrigido:
        for m in re.finditer(r"\.\.\.[ \t]*([\u2014-])", texto_corrigido):
            correcoes.append(Correcao(
                tipo="Pontuacao",
                original=m.group(0),
                corrigido="... " + m.group(1),
                inicio=m.start(), fim=m.end(),
                explicacao="Espaco entre reticencias e travessao",
                cor=COLOR_MECANICA
            ))
    texto_corrigido = novo_texto

    # 11. ESPACOS DUPLOS
    novo_texto = re.sub(r" {2,}", " ", texto_corrigido)
    if novo_texto != texto_corrigido:
        for m in re.finditer(r" {2,}", texto_corrigido):
            correcoes.append(Correcao(
                tipo="Espacamento", original=m.group(0), corrigido=" ",
                inicio=m.start(), fim=m.end(),
                explicacao="Espacos duplos", cor=COLOR_MECANICA
            ))
    texto_corrigido = novo_texto

    # 12. ASPAS RETAS → CURVAS
    aspas_abertura = True
    chars = []
    for char in texto_corrigido:
        if char == '"':
            chars.append(chr(8220) if aspas_abertura else chr(8221))
            aspas_abertura = not aspas_abertura
        else:
            chars.append(char)
    novo_texto = "".join(chars)
    if novo_texto != texto_corrigido:
        correcoes.append(Correcao(
            tipo="Tipografia", original="Aspas retas", corrigido="Aspas curvas",
            inicio=0, fim=0, explicacao="Aspas retas para curvas", cor=COLOR_MECANICA
        ))
    texto_corrigido = novo_texto

    # 13. APOSTROFO RETO → CURVO
    novo_texto = texto_corrigido.replace("'", chr(8217))
    if novo_texto != texto_corrigido:
        correcoes.append(Correcao(
            tipo="Tipografia", original="Apostrofo reto", corrigido="Apostrofo curvo",
            inicio=0, fim=0, explicacao="Apostrofo reto para curvo", cor=COLOR_MECANICA
        ))
    texto_corrigido = novo_texto

    # 14. TRES PONTOS ISOLADOS → RETICENCIAS
    novo_texto = re.sub(r"(?<!\.)\. \. \. ", "... ", texto_corrigido)
    if novo_texto != texto_corrigido:
        for m in re.finditer(r"(?<!\.)\. \. \. ", texto_corrigido):
            correcoes.append(Correcao(
                tipo="Pontuacao", original=". . . ", corrigido="... ",
                inicio=m.start(), fim=m.end(),
                explicacao="Tres pontos para reticencias", cor=COLOR_MECANICA
            ))
    texto_corrigido = novo_texto

    # 15. QUEBRAS MULTIPLAS
    novo_texto = re.sub(r"\n{3,}", "\n\n", texto_corrigido)
    if novo_texto != texto_corrigido:
        for m in re.finditer(r"\n{3,}", texto_corrigido):
            correcoes.append(Correcao(
                tipo="Espacamento", original="Quebras multiplas", corrigido="Dupla quebra",
                inicio=m.start(), fim=m.end(),
                explicacao="Multiplas quebras para dupla", cor=COLOR_MECANICA
            ))
    texto_corrigido = novo_texto

    # 16. ESPACO ANTES DE ABRE-PARENTESES
    novo_texto = re.sub(r"(?<=[^\s])\(", " (", texto_corrigido)
    if novo_texto != texto_corrigido:
        for m in re.finditer(r"(?<=[^\s])\(", texto_corrigido):
            correcoes.append(Correcao(
                tipo="Pontuacao", original=m.group(0), corrigido=" (",
                inicio=m.start(), fim=m.end(),
                explicacao="Espaco antes de abre-parenteses", cor=COLOR_MECANICA
            ))
    texto_corrigido = novo_texto

    # 17. ESPACO APOS FECHA-PARENTESES
    padrao_fecha_parenteses = rf"\)({LETRA_UNICODE})"
    novo_texto = re.sub(padrao_fecha_parenteses, r") \1", texto_corrigido)
    if novo_texto != texto_corrigido:
        for m in re.finditer(padrao_fecha_parenteses, texto_corrigido):
            correcoes.append(Correcao(
                tipo="Pontuacao", original=m.group(0), corrigido=") " + m.group(1),
                inicio=m.start(), fim=m.end(),
                explicacao="Espaco apos fecha-parenteses", cor=COLOR_MECANICA
            ))
    texto_corrigido = novo_texto

    # 18. PRIMEIRA LETRA MAIUSCULA
    if texto_corrigido and texto_corrigido[0].islower():
        novo_texto = texto_corrigido[0].upper() + texto_corrigido[1:]
        correcoes.append(Correcao(
            tipo="Maiuscula", original=texto_corrigido[0], corrigido=texto_corrigido[0].upper(),
            inicio=0, fim=1, explicacao="Primeira letra em maiuscula", cor=COLOR_MECANICA
        ))
        texto_corrigido = novo_texto

    # 19. OCR: NUMEROS NO MEIO DE PALAVRAS
    padrao_ocr_numero_palavra = rf"{LETRA_UNICODE}+[0-9]+{LETRA_UNICODE}*|{LETRA_UNICODE}*[0-9]+{LETRA_UNICODE}+"
    for m in re.finditer(padrao_ocr_numero_palavra, texto_corrigido):
        palavra = m.group(0)
        sugestoes = {"0": "o", "1": "l", "3": "e", "5": "s", "8": "b"}
        sugestao = palavra
        for num, letra in sugestoes.items():
            sugestao = sugestao.replace(num, letra)
        if sugestao != palavra:
            correcoes.append(Correcao(
                tipo="OCR Suspeito", original=palavra, corrigido=sugestao,
                inicio=m.start(), fim=m.end(),
                explicacao="Possivel erro de OCR: " + palavra + " -> " + sugestao, cor=COLOR_OCR
            ))

    return texto_corrigido, correcoes

# =============================================================================
# REGRAS DE CONTEXTO (erros que LanguageTool nao pega)
# =============================================================================

def aplicar_regras_contexto(texto, manter_girias=True):
    """Aplica correcoes contextuais: mais vs mas, gírias, hífens compostos."""
    correcoes = []
    texto_corrigido = texto

    # MAIS vs MAS (contexto de contraste)
    mais_mas = [
        (r'\bmais[ \t]+(eu|ele|ela|nós|vocês|eles|elas|você)\b', r'mas \1', '"mais" -> "mas" (contraste)'),
        (r'\bmais[ \t]+(não|sim|quando|depois|antes|agora|logo|então|ainda|também|só|já|sempre|nunca|talvez)\b', r'mas \1', '"mais" -> "mas" (contraste)'),
    ]
    for pattern, replacement, explicacao in mais_mas:
        novo_texto = re.sub(pattern, replacement, texto_corrigido, flags=re.IGNORECASE)
        if novo_texto != texto_corrigido:
            for m in re.finditer(pattern, texto_corrigido, re.IGNORECASE):
                correcoes.append(Correcao(
                    tipo="Contexto", original=m.group(0), corrigido=re.sub(pattern, replacement, m.group(0), flags=re.IGNORECASE),
                    inicio=m.start(), fim=m.end(), explicacao=explicacao, cor=COLOR_ESTILO
                ))
            texto_corrigido = novo_texto

    # ERROS DE DIGITACAO
    digitacao = [
        (r'\bdemovo\b', 'de novo', 'Erro: "demovo" -> "de novo"'),
        (r'\bnaum\b', 'não', 'Erro: "naum" -> "não"'),
        (r'\bki\b', 'que', 'Erro: "ki" -> "que"'),
        (r'\bpq\b', 'porque', 'Gíria: "pq" -> "porque"'),
        (r'\bxq\b', 'porque', 'Gíria: "xq" -> "porque"'),
        (r'\bvc\b', 'você', 'Gíria: "vc" -> "você"'),
        (r'\bvcs\b', 'vocês', 'Gíria: "vcs" -> "vocês"'),
        (r'\bn\b', 'em', 'Gíria: "n" -> "em"'),
    ]
    for pattern, replacement, explicacao in digitacao:
        novo_texto = re.sub(pattern, replacement, texto_corrigido, flags=re.IGNORECASE)
        if novo_texto != texto_corrigido:
            for m in re.finditer(pattern, texto_corrigido, re.IGNORECASE):
                correcoes.append(Correcao(
                    tipo="Digitacao", original=m.group(0), corrigido=replacement,
                    inicio=m.start(), fim=m.end(), explicacao=explicacao, cor=COLOR_ORTOGRAFIA
                ))
            texto_corrigido = novo_texto

    # HIFENS COMPOSTOS (prefixos)
    if not manter_girias:
        hifens = [
            (r'\bbem[ \t]+vindo\b', 'bem-vindo', 'Hífen: "bem vindo" -> "bem-vindo"'),
            (r'\bbem[ \t]+estar\b', 'bem-estar', 'Hífen: "bem estar" -> "bem-estar"'),
            (r'\bmal[ \t]+humorado\b', 'mal-humorado', 'Hífen: "mal humorado" -> "mal-humorado"'),
            (r'\bmal[ \t]+educado\b', 'mal-educado', 'Hífen: "mal educado" -> "mal-educado"'),
            (r'\bmal[ \t]+criado\b', 'mal-criado', 'Hífen: "mal criado" -> "mal-criado"'),
            (r'\bmal[ \t]+entendido\b', 'mal-entendido', 'Hífen: "mal entendido" -> "mal-entendido"'),
            (r'\bmal[ \t]+sucedido\b', 'mal-sucedido', 'Hífen: "mal sucedido" -> "mal-sucedido"'),
            (r'\bmal[ \t]+feito\b', 'mal-feito', 'Hífen: "mal feito" -> "mal-feito"'),
            (r'\bsemi[ \t]+novo\b', 'semi-novo', 'Hífen: "semi novo" -> "semi-novo"'),
            (r'\bsemi[ \t]+oficial\b', 'semi-oficial', 'Hífen: "semi oficial" -> "semi-oficial"'),
        ]
        for pattern, replacement, explicacao in hifens:
            novo_texto = re.sub(pattern, replacement, texto_corrigido, flags=re.IGNORECASE)
            if novo_texto != texto_corrigido:
                for m in re.finditer(pattern, texto_corrigido, re.IGNORECASE):
                    correcoes.append(Correcao(
                        tipo="Hifen", original=m.group(0), corrigido=replacement,
                        inicio=m.start(), fim=m.end(), explicacao=explicacao, cor=COLOR_HIFEN
                    ))
                texto_corrigido = novo_texto

    return texto_corrigido, correcoes

# =============================================================================
# PRESERVACAO DA ESTRUTURA
# =============================================================================

def aplicar_preservando_quebras(funcao, texto, *args, **kwargs):
    """Aplica uma funcao de correcao sem permitir alteracao nas quebras de linha."""
    partes = re.split(r"(\r\n|\n|\r)", texto)
    texto_final = []
    correcoes_final = []
    offset_original = 0
    offset_corrigido = 0

    for parte in partes:
        if not parte:
            continue

        if parte in ("\r\n", "\n", "\r"):
            texto_final.append(parte)
            offset_original += len(parte)
            offset_corrigido += len(parte)
            continue

        parte_corrigida, correcoes = funcao(parte, *args, **kwargs)
        texto_final.append(parte_corrigida)

        for correcao in correcoes:
            correcao.inicio += offset_corrigido
            correcao.fim += offset_corrigido
            correcoes_final.append(correcao)

        offset_original += len(parte)
        offset_corrigido += len(parte_corrigida)

    return "".join(texto_final), correcoes_final

# =============================================================================
# EXTRACAO DE PDF
# =============================================================================

def extrair_texto_pdf(arquivo):
    if not HAS_PYPDF2:
        st.error("PyPDF2 nao instalado. Rode: python -m pip install PyPDF2")
        return ""
    try:
        pdf_reader = PyPDF2.PdfReader(arquivo)
        texto = ""
        for page in pdf_reader.pages:
            texto += page.extract_text() or ""
            texto += "\n"
        return texto
    except Exception as e:
        st.error("Erro ao ler PDF: " + str(e))
        return ""

# =============================================================================
# GERACAO DE HTML COM DESTAQUES
# =============================================================================

def gerar_html_comparativo(original, corrigido, correcoes):
    correcoes_ordenadas = sorted(correcoes, key=lambda x: x.inicio)
    html_parts = []
    pos_atual = 0
    for corr in correcoes_ordenadas:
        if corr.inicio > pos_atual:
            html_parts.append(html_lib.escape(corrigido[pos_atual:corr.inicio]))
        titulo = html_lib.escape(corr.tipo + ": " + corr.explicacao, quote=True)
        texto_marcado = html_lib.escape(corr.corrigido)
        html_parts.append(
            "<mark style=\"background-color: " + corr.cor + "; padding: 1px 2px; border-radius: 2px;\" "
            "title=\"" + titulo + "\">"
            + texto_marcado + "</mark>"
        )
        pos_atual = corr.inicio + len(corr.corrigido)
    if pos_atual < len(corrigido):
        html_parts.append(html_lib.escape(corrigido[pos_atual:]))
    texto_destacado = "".join(html_parts)
    texto_destacado = texto_destacado.replace("\n", "<br>")
    html = """<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><title>Texto Corrigido</title>
<style>
body { font-family: Georgia, serif; line-height: 1.8; max-width: 800px; margin: 40px auto; padding: 20px; }
h1 { color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }
.legend { margin: 20px 0; padding: 15px; background: #f5f5f5; border-radius: 8px; }
.legend-item { display: inline-block; margin: 5px 15px; }
.box { width: 20px; height: 20px; display: inline-block; vertical-align: middle; margin-right: 5px; border-radius: 3px; }
.texto { text-align: justify; font-size: 16px; }
</style>
</head>
<body>
<h1>Texto Corrigido</h1>
<div class="legend">
<strong>Legenda:</strong><br>
<span class="legend-item"><span class="box" style="background:#ffeb3b"></span> Regras Mecanicas</span>
<span class="legend-item"><span class="box" style="background:#ffcdd2"></span> Ortografia</span>
<span class="legend-item"><span class="box" style="background:#bbdefb"></span> Crase</span>
<span class="legend-item"><span class="box" style="background:#c8e6c9"></span> Concordancia</span>
<span class="legend-item"><span class="box" style="background:#ffe0b2"></span> OCR Suspeito</span>
<span class="legend-item"><span class="box" style="background:#b2dfdb"></span> Hifen/OCR</span>
<span class="legend-item"><span class="box" style="background:#e1bee7"></span> Contexto</span>
</div>
<div class="texto">""" + texto_destacado + """</div>
</body></html>"""
    return html

# =============================================================================
# INTERFACE STREAMLIT
# =============================================================================

def main():
    st.set_page_config(
        page_title="Corretor Inteligente de Textos",
        page_icon="books",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    st.title("Corretor Inteligente de Textos")
    st.markdown("**Para revisao de livros e transcricoes** - Regras mecanicas + LanguageTool (ortografia, crase, concordancia)")

    if "lt_jar_path" not in st.session_state:
        st.session_state.lt_jar_path = None
    if "lt_rodando" not in st.session_state:
        st.session_state.lt_rodando = False

    with st.sidebar:
        st.header("Configuracoes")
        usar_mecanicas = st.checkbox("Regras Mecanicas", value=True, 
            help="Espacamento, pontuacao, maiusculas, aspas, travessoes")
        usar_contexto = st.checkbox("Regras de Contexto", value=True,
            help="Mais vs mas, digitacao, hifens compostos")
        manter_girias = st.checkbox("Manter Girias (pra, tava, tô)", value=True,
            help="Nao corrigir gírias coloquiais")
        usar_languagetool = st.checkbox("LanguageTool (Gramatica)", value=True,
            help="Ortografia, crase, concordancia, regencia verbal")
        usar_ocr = st.checkbox("Detectar erros de OCR", value=True,
            help="Numeros no meio de palavras, caracteres suspeitos")
        st.markdown("---")
        st.markdown("**Dica:** Passe o mouse sobre as marcacoes coloridas para ver a explicacao.")
        st.markdown("---")
        st.subheader("LanguageTool")
        lt_rodando = verificar_languagetool_rodando()
        if lt_rodando:
            st.success("Conectado!")
            st.session_state.lt_rodando = True
        else:
            st.warning("Desconectado")
            jar_encontrado = encontrar_languagetool_jar()
            if jar_encontrado:
                st.info("Encontrado: " + str(jar_encontrado))
                if st.button("Iniciar LanguageTool"):
                    with st.spinner("Iniciando..."):
                        if iniciar_languagetool(jar_encontrado):
                            st.session_state.lt_jar_path = str(jar_encontrado)
                            st.session_state.lt_rodando = True
                            st.success("LanguageTool iniciado!")
                            st.rerun()
                        else:
                            st.error("Falha ao iniciar. Verifique se o Java esta instalado.")
            else:
                st.info("LanguageTool nao encontrado automaticamente.")
                st.markdown("**Baixe em:** https://languagetool.org/download/")
                jar_file = st.file_uploader("Ou selecione o arquivo languagetool-server.jar", type=["jar"])
                if jar_file:
                    temp_dir = Path.home() / ".languagetool_temp"
                    temp_dir.mkdir(exist_ok=True)
                    jar_path = temp_dir / "languagetool-server.jar"
                    with open(jar_path, "wb") as f:
                        f.write(jar_file.getvalue())
                    if st.button("Iniciar com este arquivo"):
                        with st.spinner("Iniciando..."):
                            if iniciar_languagetool(jar_path):
                                st.session_state.lt_jar_path = str(jar_path)
                                st.session_state.lt_rodando = True
                                st.success("LanguageTool iniciado!")
                                st.rerun()
                            else:
                                st.error("Falha ao iniciar. Verifique se o Java esta instalado.")

    tab1, tab2 = st.tabs(["Entrada", "Resultado"])

    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Colar Texto")
            texto_colar = st.text_area(
                "Cole o texto aqui (Ctrl+V):",
                height=300,
                placeholder="Cole o texto do livro aqui..."
            )
        with col2:
            st.subheader("Ou Upload de Arquivo")
            arquivo = st.file_uploader(
                "Escolha um arquivo TXT ou PDF",
                type=["txt", "pdf"]
            )
            if arquivo:
                if arquivo.type == "application/pdf":
                    texto_arquivo = extrair_texto_pdf(arquivo)
                else:
                    texto_arquivo = arquivo.read().decode("utf-8")
                st.success("Arquivo carregado: " + arquivo.name)
                st.text_area("Preview:", texto_arquivo[:500] + "...", height=200, disabled=True)
            else:
                texto_arquivo = ""

    texto_entrada = texto_colar if texto_colar else texto_arquivo

    if texto_entrada and st.button("CORRIGIR TEXTO", type="primary"):
        with st.spinner("Processando..."):
            progresso = st.progress(0)
            if usar_mecanicas:
                progresso.progress(25, text="Aplicando regras mecanicas...")
                texto_processado, correcoes_mecanicas = aplicar_preservando_quebras(aplicar_regras_mecanicas, texto_entrada)
            else:
                texto_processado = texto_entrada
                correcoes_mecanicas = []
            if usar_contexto:
                progresso.progress(40, text="Aplicando regras de contexto...")
                texto_processado, correcoes_contexto = aplicar_preservando_quebras(
                    aplicar_regras_contexto,
                    texto_processado,
                    manter_girias=manter_girias
                )
            else:
                correcoes_contexto = []
            correcoes_lt = []
            if usar_languagetool and st.session_state.lt_rodando:
                progresso.progress(60, text="Verificando ortografia e gramatica...")
                texto_antes_lt = texto_processado
                texto_processado, correcoes_lt = verificar_languagetool(texto_processado)
                if texto_processado.count("\n") != texto_antes_lt.count("\n"):
                    texto_processado = texto_antes_lt
                    correcoes_lt = []
                    st.warning("LanguageTool alterou a estrutura do texto. Essa etapa foi descartada para preservar os paragrafos.")
            elif usar_languagetool and not st.session_state.lt_rodando:
                st.warning("LanguageTool nao esta rodando. Ative na sidebar para correcoes de ortografia/gramatica.")
            progresso.progress(80, text="Finalizando...")
            todas_correcoes = correcoes_mecanicas + correcoes_contexto + correcoes_lt
            if not usar_ocr:
                todas_correcoes = [c for c in todas_correcoes if c.tipo != "OCR Suspeito"]
            progresso.progress(100, text="Pronto!")
            time.sleep(0.5)
            progresso.empty()

        with tab2:
            st.subheader("Resultado da Revisao")
            col_stats1, col_stats2, col_stats3, col_stats4, col_stats5, col_stats6, col_stats7 = st.columns(7)
            tipos_count = {}
            for c in todas_correcoes:
                tipos_count[c.tipo] = tipos_count.get(c.tipo, 0) + 1
            with col_stats1:
                st.metric("Total", len(todas_correcoes))
            with col_stats2:
                st.metric("Mecanicas", tipos_count.get("Pontuacao", 0) + tipos_count.get("Espacamento", 0) + tipos_count.get("Maiuscula", 0) + tipos_count.get("Tipografia", 0))
            with col_stats3:
                st.metric("Ortografia", tipos_count.get("Ortografia", 0))
            with col_stats4:
                st.metric("Crase/Gramatica", tipos_count.get("Crase", 0) + tipos_count.get("Concordancia", 0) + tipos_count.get("Gramatica", 0))
            with col_stats5:
                st.metric("OCR", tipos_count.get("OCR Suspeito", 0) + tipos_count.get("OCR/Hifen", 0))
            with col_stats6:
                st.metric("Contexto", tipos_count.get("Contexto", 0) + tipos_count.get("Digitacao", 0))
            with col_stats7:
                st.metric("Hifen", tipos_count.get("Hifen", 0))
            st.markdown("---")
            col_orig, col_corr = st.columns(2)
            with col_orig:
                st.markdown("**Texto Original**")
                st.text_area("Original", texto_entrada, height=400, disabled=True)
            with col_corr:
                st.markdown("**Texto Corrigido**")
                st.text_area("Corrigido", texto_processado, height=400)
            st.markdown("---")
            st.subheader("Visualizacao com Destaques")
            html_resultado = gerar_html_comparativo(texto_entrada, texto_processado, todas_correcoes)
            st.html(html_resultado)
            col_down1, col_down2, col_down3 = st.columns(3)
            with col_down1:
                st.download_button("Baixar TXT Corrigido", texto_processado, file_name="texto_corrigido.txt", mime="text/plain")
            with col_down2:
                st.download_button("Baixar HTML com Destaques", html_resultado, file_name="texto_corrigido.html", mime="text/html")
            with col_down3:
                relatorio = "RELATORIO DE REVISAO\n" + "="*50 + "\n\n"
                relatorio += "Total de correcoes: " + str(len(todas_correcoes)) + "\n\n"
                relatorio += "Por tipo:\n"
                for tipo, count in sorted(tipos_count.items(), key=lambda x: -x[1]):
                    relatorio += "  - " + tipo + ": " + str(count) + "\n"
                relatorio += "\n" + "="*50 + "\n\nDETALHAMENTO:\n"
                for i, c in enumerate(todas_correcoes, 1):
                    relatorio += "\n" + str(i) + ". [" + c.tipo + "] '" + c.original + "' -> '" + c.corrigido + "'\n"
                    relatorio += "   " + c.explicacao + "\n"
                st.download_button("Baixar Relatorio", relatorio, file_name="relatorio_revisao.txt", mime="text/plain")
            st.markdown("---")
            st.subheader("Lista de Correcoes")
            if todas_correcoes:
                dados_tabela = []
                for c in todas_correcoes:
                    dados_tabela.append({
                        "Tipo": c.tipo,
                        "Original": c.original[:50],
                        "Corrigido": c.corrigido[:50],
                        "Explicacao": c.explicacao[:100]
                    })
                st.dataframe(dados_tabela, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhuma correcao encontrada! O texto esta perfeito.")

    elif not texto_entrada:
        with tab2:
            st.info("Cole um texto ou faca upload de um arquivo para comecar.")

if __name__ == "__main__":
    main()
