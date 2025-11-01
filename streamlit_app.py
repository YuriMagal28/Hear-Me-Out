import streamlit as st
import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import base64
from datetime import datetime
import os
import json
import uuid
import re

# ==================== CONFIGURATION ====================
st.set_page_config(
    page_title="HEAR ME OUT - Modo Festa 🎉",
    page_icon="🗣️",
    layout="wide"
)

# SerpAPI key hardcoded (como no seu código original; ideal: st.secrets)
SERPAPI_KEY = "021124766e0086f0bbe720bff0d01d3b1977f5b447240c8a1c82728e2e3b0482"

# ==================== PERSISTÊNCIA EM DISCO ====================

DATA_DIR = "party_data"
IMG_DIR = os.path.join(DATA_DIR, "images")
META_DIR = os.path.join(DATA_DIR, "entries")

def ensure_storage():
    os.makedirs(IMG_DIR, exist_ok=True)
    os.makedirs(META_DIR, exist_ok=True)

def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[-\s]+", "_", text, flags=re.UNICODE)
    return text.strip("_")[:40] or "item"

def atomic_write_json(path: str, payload: dict):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def save_entry_to_disk(character: str, guest: str, pil_image: Image.Image, source: str):
    ensure_storage()
    now = datetime.now()
    uid = uuid.uuid4().hex[:8]
    slug = slugify(character)
    ts_compact = now.strftime("%Y%m%d-%H%M%S")

    img_filename = f"{ts_compact}_{uid}_{slug}.png"
    img_path = os.path.join(IMG_DIR, img_filename)
    pil_image.save(img_path, format="PNG")

    meta = {
        "id": f"{ts_compact}-{uid}",
        "character": character,
        "guest": guest or "Anônimo",
        "timestamp": now.strftime("%H:%M:%S"),
        "source": source or "",
        "image_path": img_path,
        "created_at": now.isoformat()
    }
    meta_path = os.path.join(META_DIR, f"{ts_compact}_{uid}.json")
    atomic_write_json(meta_path, meta)
    return meta

def load_entries_from_disk():
    ensure_storage()
    entries = []
    for name in sorted(os.listdir(META_DIR)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(META_DIR, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            # garante que a imagem existe
            if meta.get("image_path") and os.path.exists(meta["image_path"]):
                entries.append(meta)
        except Exception:
            continue
    # ordena por criação (asc)
    entries.sort(key=lambda m: m.get("created_at", ""))
    return entries

def clear_all_disk_data():
    # Remove arquivos e reseta estado
    for folder in (IMG_DIR, META_DIR):
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                try:
                    os.remove(os.path.join(folder, name))
                except Exception:
                    pass

# ==================== IMAGE SEARCH WITH SERPAPI ====================

def search_google_images(query, api_key):
    try:
        url = "https://serpapi.com/search"
        params = {
            "engine": "google_images",
            "q": query,
            "api_key": api_key,
            "num": 5,
            "safe": "active"
        }
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        if "images_results" in data and len(data["images_results"]) > 0:
            for result in data["images_results"][:5]:
                image_url = result.get("original") or result.get("thumbnail")
                if image_url:
                    try:
                        img_response = requests.get(
                            image_url,
                            timeout=10,
                            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                        )
                        if img_response.status_code == 200:
                            img = Image.open(BytesIO(img_response.content))
                            img.verify()
                            img = Image.open(BytesIO(img_response.content))
                            return img, result.get("source", "Google Images")
                    except Exception:
                        continue
        return None, None
    except Exception as e:
        print(f"SerpAPI Error: {str(e)}")
        return None, None

def create_placeholder_image(text, width=1200, height=675):
    img = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        r = int(102 + (255 - 102) * (y / height))
        g = int(126 + (75 - 126) * (y / height))
        b = int(234 + (75 - 234) * (y / height))
        draw.rectangle([(0, y), (width, y + 1)], fill=(r, g, b))
    try:
        font_large = ImageFont.truetype("arial.ttf", 70)
        font_small = ImageFont.truetype("arial.ttf", 40)
    except:
        try:
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 70)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
        except:
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font_large)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (width - text_width) // 2
    y = (height - text_height) // 2 - 30
    draw.text((x + 4, y + 4), text, font=font_large, fill=(0, 0, 0, 180))
    draw.text((x, y), text, font=font_large, fill=(255, 255, 255))
    subtitle = "Imagem não encontrada"
    bbox2 = draw.textbbox((0, 0), subtitle, font=font_small)
    sub_width = bbox2[2] - bbox2[0]
    sub_x = (width - sub_width) // 2
    sub_y = y + text_height + 20
    draw.text((sub_x + 2, sub_y + 2), subtitle, font=font_small, fill=(0, 0, 0, 180))
    draw.text((sub_x, sub_y), subtitle, font=font_small, fill=(255, 255, 255, 200))
    return img

def fetch_character_image(character_name, api_key):
    if not api_key:
        st.error("⚠️ API Key não configurada! Usando placeholder…")
        return create_placeholder_image(character_name), "Placeholder"
    with st.spinner(f"🔍 Buscando '{character_name}' no Google Images..."):
        img, source = search_google_images(character_name, api_key)
        if img: 
            st.success(f"✅ Imagem encontrada! (Fonte: {source})")
            return img, source
    with st.spinner("🔍 Tentando busca alternativa..."):
        img, source = search_google_images(f"{character_name} character", api_key)
        if img:
            st.success(f"✅ Imagem encontrada! (Fonte: {source})")
            return img, source
    st.warning(f"⚠️ Não encontramos '{character_name}'. Usando placeholder.")
    return create_placeholder_image(character_name), "Placeholder"

# ==================== MEME CREATION ====================

def create_meme(image, text="HEAR ME OUT", character_name="", canvas_size=(1200, 675)):
    canvas = Image.new("RGB", canvas_size, color=(26, 26, 26))
    img_width, img_height = image.size
    canvas_width, canvas_height = canvas_size
    text_space = 150
    available_height = canvas_height - text_space
    scale = min(canvas_width / img_width, available_height / img_height)
    new_size = (int(img_width * scale), int(img_height * scale))
    try:
        image = image.resize(new_size, Image.Resampling.LANCZOS)
    except:
        image = image.resize(new_size, Image.LANCZOS)
    x_offset = (canvas_width - new_size[0]) // 2
    y_offset = text_space + (available_height - new_size[1]) // 2
    if image.mode == 'RGBA':
        background = Image.new('RGB', image.size, (26, 26, 26))
        background.paste(image, mask=image.split()[3])
        image = background
    elif image.mode != 'RGB':
        image = image.convert('RGB')
    canvas.paste(image, (x_offset, y_offset))
    draw = ImageDraw.Draw(canvas)
    try:
        main_font = ImageFont.truetype("arial.ttf", 80)
        char_font = ImageFont.truetype("arial.ttf", 50)
    except:
        try:
            main_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 80)
            char_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 50)
        except:
            main_font = ImageFont.load_default()
            char_font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=main_font)
    text_width = bbox[2] - bbox[0]
    text_x = (canvas_width - text_width) // 2
    text_y = 20
    stroke_width = 5
    for ox in range(-stroke_width, stroke_width + 1):
        for oy in range(-stroke_width, stroke_width + 1):
            if ox or oy:
                draw.text((text_x + ox, text_y + oy), text, font=main_font, fill=(0, 0, 0))
    draw.text((text_x, text_y), text, font=main_font, fill=(255, 255, 255))
    if character_name:
        char_bbox = draw.textbbox((0, 0), character_name, font=char_font)
        char_width = char_bbox[2] - char_bbox[0]
        char_x = (canvas_width - char_width) // 2
        char_y = 110
        for ox in range(-3, 4):
            for oy in range(-3, 4):
                if ox or oy:
                    draw.text((char_x + ox, char_y + oy), character_name, font=char_font, fill=(0, 0, 0))
        draw.text((char_x, char_y), character_name, font=char_font, fill=(255, 75, 75))
    return canvas

# ==================== SESSION STATE (CARREGADO A PARTIR DO DISCO) ====================
ensure_storage()
if "memes_collection" not in st.session_state:
    st.session_state.memes_collection = load_entries_from_disk()
if "current_slide" not in st.session_state:
    st.session_state.current_slide = 0

# ==================== SIDEBAR ====================
with st.sidebar:
    st.header("🎉 Modo Festa")
    mode = st.radio(
        "Escolha o Modo:",
        ["👥 Coleta (Convidados)", "🎬 Apresentação (Host)"],
        help="Coleta: Para os convidados enviarem\nApresentação: Para mostrar todos"
    )
    st.divider()
    st.metric("Total de Personagens", len(st.session_state.memes_collection))
    if mode == "🎬 Apresentação (Host)" and len(st.session_state.memes_collection) > 0:
        st.divider()
        if st.button("🗑️ Limpar Todos", type="secondary", use_container_width=True):
            clear_all_disk_data()
            st.session_state.memes_collection = []
            st.session_state.current_slide = 0
            st.rerun()
    st.divider()
    if SERPAPI_KEY:
        st.success("✅ **SerpAPI Configurado**")
        st.caption(f"Key: {SERPAPI_KEY[:8]}...{SERPAPI_KEY[-4:]}")
    else:
        st.error("❌ **API Key não configurada**")
        st.caption("Configure SERPAPI_KEY")
    st.divider()
    st.info("🔥 **Powered by Google Images**")
    st.caption("Via SerpAPI - Melhores resultados!")

# ==================== MAIN ====================

if mode == "👥 Coleta (Convidados)":
    st.title("🗣️ HEAR ME OUT")
    st.markdown("### Qual personagem você acha atraente? 😏")
    st.markdown("*Seja honesto... ninguém vai julgar (muito)!*")

    col1, col2 = st.columns([3, 1])
    with col1:
        character_name = st.text_input(
            "🎭 Nome do Personagem",
            placeholder="Ex: Shrek, Pikachu, Megamente...",
            help="Digite qualquer personagem - vamos buscar no Google!",
            key="char_input"
        )
        guest_name = st.text_input(
            "👤 Seu Nome (Opcional)",
            placeholder="Ex: Maria, João...",
            help="Para sabermos quem escolheu!",
            key="guest_input"
        )
    with col2:
        st.success("✨ **Google Images**")
        st.caption("Encontramos QUALQUER personagem!")
        st.caption("")
        st.caption("**Exemplos:**")
        st.caption("• Shrek")
        st.caption("• Mike Wazowski")
        st.caption("• Lorde Farquaad")
        st.caption("• Megamente")

    if st.button("💕 Adicionar à Lista", type="primary", use_container_width=True):
        if not character_name.strip():
            st.warning("⚠️ Por favor, digite o nome de um personagem!")
        else:
            img, source = fetch_character_image(character_name, SERPAPI_KEY)
            meme = create_meme(img, text="HEAR ME OUT", character_name=character_name)

            # >>> NOVO: salva em disco e recarrega a lista <<<
            saved_meta = save_entry_to_disk(
                character=character_name,
                guest=guest_name.strip() if guest_name else "Anônimo",
                pil_image=meme,
                source=source
            )
            st.session_state.memes_collection = load_entries_from_disk()

            st.success(f"✅ **{character_name}** adicionado à lista!")
            st.balloons()
            st.image(meme, caption=f"Adicionado por: {saved_meta['guest']}", use_container_width=True)

    st.divider()
    if len(st.session_state.memes_collection) > 0:
        st.subheader(f"📊 {len(st.session_state.memes_collection)} personagens coletados!")
        cols = st.columns(4)
        for idx, meme_data in enumerate(st.session_state.memes_collection[-8:]):
            with cols[idx % 4]:
                st.caption(f"**{meme_data['character']}**")
                st.caption(f"👤 {meme_data['guest']}")
                st.caption(f"🕐 {meme_data['timestamp']}")

else:
    st.title("🎬 Apresentação: HEAR ME OUT da Galera!")
    # sempre recarrega do disco ao entrar no modo apresentação
    st.session_state.memes_collection = load_entries_from_disk()

    if len(st.session_state.memes_collection) == 0:
        st.warning("⚠️ Nenhum personagem foi adicionado ainda!")
        st.info("👈 Volte para o modo **Coleta** e adicione alguns personagens primeiro!")
    else:
        col1, col2, col3, col4, col5 = st.columns([1, 1, 2, 1, 1])
        with col1:
            if st.button("⏮️ Primeiro", use_container_width=True):
                st.session_state.current_slide = 0
                st.rerun()
        with col2:
            if st.button("◀️ Anterior", use_container_width=True):
                if st.session_state.current_slide > 0:
                    st.session_state.current_slide -= 1
                    st.rerun()
        with col3:
            st.markdown(
                f"<h3 style='text-align: center;'>Slide {st.session_state.current_slide + 1} de {len(st.session_state.memes_collection)}</h3>",
                unsafe_allow_html=True
            )
        with col4:
            if st.button("▶️ Próximo", use_container_width=True):
                if st.session_state.current_slide < len(st.session_state.memes_collection) - 1:
                    st.session_state.current_slide += 1
                    st.rerun()
        with col5:
            if st.button("⏭️ Último", use_container_width=True):
                st.session_state.current_slide = len(st.session_state.memes_collection) - 1
                st.rerun()

        st.divider()

        current_meme = st.session_state.memes_collection[st.session_state.current_slide]
        st.markdown(
            f"<h1 style='text-align: center; color: #FF4B4B; font-size: 3.5em;'>🎭 {current_meme['character']}</h1>",
            unsafe_allow_html=True
        )
        st.markdown(
            f"<h2 style='text-align: center; color: #666;'>Escolhido por: <span style='color: #FF4B4B;'>{current_meme['guest']}</span></h2>",
            unsafe_allow_html=True
        )
        st.markdown(
            f"<p style='text-align: center; color: #999;'>⏰ {current_meme['timestamp']}</p>",
            unsafe_allow_html=True
        )

        # >>> AGORA CARREGA PELO CAMINHO DO ARQUIVO <<<
        meme_img = Image.open(current_meme['image_path'])
        st.image(meme_img, use_container_width=True)

        col_dl1, col_dl2, col_dl3 = st.columns([1, 2, 1])
        with col_dl2:
            meme_bytes = BytesIO()
            meme_img.save(meme_bytes, format='PNG')
            st.download_button(
                label="⬇️ Baixar este Meme",
                data=meme_bytes.getvalue(),
                file_name=f"hear_me_out_{slugify(current_meme['character'])}.png",
                mime="image/png",
                use_container_width=True,
                type="primary"
            )

        st.divider()
        st.subheader("📸 Galeria Completa")

        cols = st.columns(5)
        for idx, meme_data in enumerate(st.session_state.memes_collection):
            with cols[idx % 5]:
                try:
                    mini_img = Image.open(meme_data['image_path'])
                    st.image(mini_img, use_container_width=True)
                except Exception:
                    st.caption("Imagem indisponível")
                if st.button(
                    f"{meme_data['character'][:15]}",
                    key=f"thumb_{idx}",
                    use_container_width=True,
                    type="secondary" if idx != st.session_state.current_slide else "primary"
                ):
                    st.session_state.current_slide = idx
                    st.rerun()
                st.caption(f"👤 {meme_data['guest']}")

st.divider()
st.caption("Made with ❤️ for your party | Powered by SerpAPI + Google Images")
