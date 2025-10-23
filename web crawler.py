import os
import time
import json
import hashlib
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from newspaper import Article
from bs4 import BeautifulSoup

# ======================== CONFIGURAÇÃO ========================
USUARIO_AGENTE = 'RastreadorNoticias/1.0 (+https://example.com)'
CABECALHOS = {'User-Agent': USUARIO_AGENTE}
TEMPO_LIMITE_REQUISICAO = 10
INTERVALO_ENTRE_REQUISICOES = 1.0
DIRETORIO_SAIDA = 'saida'
DIRETORIO_IMAGENS = os.path.join(DIRETORIO_SAIDA, 'imagens')

FEEDS_RSS = [
    'https://g1.globo.com/rss/g1/tecnologia/',
    'https://rss.app/feeds/tzsWys2U6rj4mrqc.xml',
    'https://rss.app/feeds/zdt1qrt08NPr3QJz.xml',
    
]


def garantir_diretorios():
    os.makedirs(DIRETORIO_SAIDA, exist_ok=True)
    os.makedirs(DIRETORIO_IMAGENS, exist_ok=True)

def salvar_json(nome_arquivo, dados):
    with open(nome_arquivo, 'w', encoding='utf-8') as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)

def gerar_slug(texto: str) -> str:
    texto_limpo = ''.join(c if c.isalnum() else '_' for c in texto).strip('_')
    if len(texto_limpo) == 0:
        texto_limpo = hashlib.md5(texto.encode('utf-8')).hexdigest()[:8]
    return texto_limpo[:120]

def buscar_url(url: str):
    try:
        resposta = requests.get(url, headers=CABECALHOS, timeout=TEMPO_LIMITE_REQUISICAO)
        resposta.raise_for_status()
        return resposta
    except Exception as erro:
        print(f"Erro ao buscar {url}: {erro}")
        return None

def analisar_artigo_newspaper(url: str):
    """Tenta extrair informações completas com newspaper3k."""
    try:
        artigo = Article(url, language='pt')
        artigo.download()
        artigo.parse()
        artigo.nlp()
        dados_artigo = {
            'url': url,
            'titulo': artigo.title,
            'texto': artigo.text,
            'resumo': artigo.summary if hasattr(artigo, 'summary') else None,
            'imagem_principal': artigo.top_image if hasattr(artigo, 'top_image') else None,
            'imagens': list(artigo.images) if hasattr(artigo, 'images') else [],
        }
        return dados_artigo
    except Exception as erro:
        print(f"newspaper3k falhou para {url}: {erro}")
        return None

def analisar_artigo_fallback(url: str, html_texto: str):
    """Fallback manual com BeautifulSoup caso newspaper3k falhe."""
    sopa = BeautifulSoup(html_texto, 'lxml')

    titulo_tag = sopa.find('meta', property='og:title') or sopa.find('title')
    titulo = titulo_tag.get('content') if titulo_tag and titulo_tag.has_attr('content') else (titulo_tag.string if titulo_tag else '')

    descricao_tag = sopa.find('meta', property='og:description') or sopa.find('meta', attrs={'name': 'description'})
    descricao = descricao_tag.get('content') if descricao_tag and descricao_tag.has_attr('content') else None

    imagens = []
    og_imagem = sopa.find('meta', property='og:image')
    if og_imagem and og_imagem.get('content'):
        imagens.append(urljoin(url, og_imagem.get('content')))

    for img in sopa.find_all('img', src=True):
        src = img['src']
        completo = urljoin(url, src)
        if completo not in imagens:
            imagens.append(completo)
        if len(imagens) >= 5:
            break

    return {
        'url': url,
        'titulo': titulo.strip() if titulo else '',
        'resumo': descricao,
        'imagem_principal': imagens[0] if imagens else None,
        'imagens': imagens,
    }

def baixar_imagem(url_imagem: str):
    try:
        resposta = requests.get(url_imagem, headers=CABECALHOS, timeout=TEMPO_LIMITE_REQUISICAO)
        resposta.raise_for_status()
        extensao = os.path.splitext(urlparse(url_imagem).path)[1].split('?')[0]
        if not extensao or len(extensao) > 6:
            extensao = '.jpg'
        nome_arquivo = gerar_slug(url_imagem) + extensao
        caminho = os.path.join(DIRETORIO_IMAGENS, nome_arquivo)
        with open(caminho, 'wb') as arquivo:
            arquivo.write(resposta.content)
        return caminho
    except Exception as erro:
        print(f"Falha ao baixar imagem {url_imagem}: {erro}")
        return None

def processar_feed(url_feed: str, max_noticias=10):
    print(f"Processando feed: {url_feed}")
    feed = feedparser.parse(url_feed)
    resultados = []

    for entrada in feed.entries[:max_noticias]:
        noticia = {
            'feed': url_feed,
            'titulo': entrada.get('title'),
            'link': entrada.get('link'),
            'publicado': entrada.get('published'),
            'resumo': entrada.get('summary') if 'summary' in entrada else None,
        }

        url = noticia['link']
        time.sleep(INTERVALO_ENTRE_REQUISICOES)
        resposta = buscar_url(url)

        if resposta and resposta.text:
            artigo = analisar_artigo_newspaper(url)
            if not artigo:
                artigo = analisar_artigo_fallback(url, resposta.text)

            noticia.update(artigo)

            if noticia.get('imagem_principal'):
                caminho_imagem = baixar_imagem(noticia['imagem_principal'])
                if caminho_imagem:
                    noticia['imagem_principal_local'] = caminho_imagem

        resultados.append(noticia)

    return resultados

def rastrear_todos(feeds_rss, nome_arquivo_saida=None):
    garantir_diretorios()
    todas_noticias = []

    for feed in feeds_rss:
        try:
            noticias = processar_feed(feed)
            todas_noticias.extend(noticias)
        except Exception as erro:
            print(f"Erro ao processar o feed {feed}: {erro}")

    timestamp = int(time.time())
    if not nome_arquivo_saida:
        nome_arquivo_saida = os.path.join(DIRETORIO_SAIDA, f'noticias_{timestamp}.json')

    salvar_json(nome_arquivo_saida, todas_noticias)
    print(f"Salvas {len(todas_noticias)} notícias em {nome_arquivo_saida}")
    return nome_arquivo_saida

if __name__ == '__main__':
    arquivo_saida = rastrear_todos(FEEDS_RSS)
    print('Pronto.')
