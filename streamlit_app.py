import streamlit as st
import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from datetime import datetime
import os, json, uuid, re, time
import streamlit.components.v1 as components

# ==================== CONFIGURAÇÃO ====================
st.set_page_config(page_title="HEAR ME OUT - Modo Festa 🎉", page_icon="🗣️", layout="wide")

# --- compat de rerun entre versões do Streamlit ---
def do_rerun():
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()

# --- helpers de query params (para teclas) ---
def _get_qparams():
    try:
        return dict(st.query_params)
    except Exception:
        return {k: v[0] if isinstance(v, list) else v for k, v in st.experimental_get_query_params().items()}

def _set_qparams(d: dict):
    # substitui por d (limpa + define)
    try:
        st.query_params.clear()
        for k, v in d.items():
            if v is not None:
                st.query_params[k] = v
    except Exception:
        st.experimental_set_query_params(**{k: v for k, v in d.items() if v is not None})

def _clear_qparams():
    _set_qparams({})

# SerpAPI key (mantenha como quiser; ideal: st.secrets["SERPAPI_KEY"])
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
    ts = now.strftime("%Y%m%d-%H%M%S")
    img_path = os.path.join(IMG_DIR, f"{ts}_{uid}_{slug}.png")
    pil_image.save(img_path, format="PNG")
    meta = {
        "id": f"{ts}-{uid}",
        "character": character,
        "guest": guest or "Anônimo",
        "timestamp": now.strftime("%H:%M:%S"),
        "source": source or "",
        "image_path": img_path,
        "created_at": now.isoformat()
    }
    atomic_write_json(os.path.join(META_DIR, f"{ts}_{uid}.json"), meta)
    return meta

def load_entries_from_disk():
    ensure_storage()
    entries = []
    for name in sorted(os.listdir(META_DIR)):
        if name.endswith(".json"):
            try:
                with open(os.path.join(META_DIR, name), "r", encoding="utf-8") as f:
                    meta = json.load(f)
                if meta.get("image_path") and os.path.exists(meta["image_path"]):
                    entries.append(meta)
            except Exception:
                pass
    entries.sort(key=lambda m: m.get("created_at", ""))
    return entries

def clear_all_disk_data():
    for folder in (IMG_DIR, META_DIR):
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                try:
                    os.remove(os.path.join(folder, name))
                except Exception:
                    pass

# ==================== BUSCA DE IMAGEM ====================
def search_google_images(query, api_key):
    try:
        url = "https://serpapi.com/search"
        params = {"engine": "google_images", "q": query, "api_key": api_key, "num": 5, "safe": "active"}
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if "images_results" in data and data["images_results"]:
            for r in data["images_results"][:5]:
                image_url = r.get("original") or r.get("thumbnail")
                if not image_url:
                    continue
                try:
                    ir = requests.get(image_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                    if ir.status_code == 200:
                        img = Image.open(BytesIO(ir.content))
                        img.verify()
                        img = Image.open(BytesIO(ir.content))
                        return img, r.get("source", "Google Images")
                except Exception:
                    continue
        return None, None
    except Exception as e:
        print("SerpAPI error:", e)
        return None, None

def create_placeholder_image(text, width=1200, height=675):
    img = Image.new('RGB', (width, height))
    d = ImageDraw.Draw(img)
    for y in range(height):
        r = int(102 + (255 - 102) * (y / height))
        g = int(126 + (75 - 126) * (y / height))
        b = int(234 + (75 - 234) * (y / height))
        d.rectangle([(0, y), (width, y + 1)], fill=(r, g, b))
    try:
        font_large = ImageFont.truetype("arial.ttf", 70)
        font_small = ImageFont.truetype("arial.ttf", 40)
    except:
        try:
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 70)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
        except:
            font_large = ImageFont.load_default(); font_small = ImageFont.load_default()
    bbox = d.textbbox((0, 0), text, font=font_large)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    x, y = (width - tw)//2, (height - th)//2 - 30
    d.text((x+4, y+4), text, font=font_large, fill=(0,0,0,180))
    d.text((x, y), text, font=font_large, fill=(255,255,255))
    subtitle = "Imagem não encontrada"
    bbox2 = d.textbbox((0,0), subtitle, font=font_small)
    sub_x = (width - (bbox2[2]-bbox2[0]))//2
    d.text((sub_x+2, y+th+22), subtitle, font=font_small, fill=(0,0,0,180))
    d.text((sub_x, y+th+20), subtitle, font=font_small, fill=(255,255,255,200))
    return img

def fetch_character_image(name, api_key):
    if not api_key:
        st.error("⚠️ API Key não configurada! Usando placeholder…")
        return create_placeholder_image(name), "Placeholder"
    with st.spinner(f"🔍 Buscando '{name}' no Google Images..."):
        img, src = search_google_images(name, api_key)
        if img: 
            st.success(f"✅ Imagem encontrada! (Fonte: {src})")
            return img, src
    with st.spinner("🔍 Tentando busca alternativa..."):
        img, src = search_google_images(f"{name} character", api_key)
        if img:
            st.success(f"✅ Imagem encontrada! (Fonte: {src})")
            return img, src
    st.warning(f"⚠️ Não encontramos '{name}'. Usando placeholder.")
    return create_placeholder_image(name), "Placeholder"

# ==================== CRIA MEME ====================
def create_meme(image, text="HEAR ME OUT", character_name="", canvas_size=(1200, 675)):
    canvas = Image.new("RGB", canvas_size, color=(26, 26, 26))
    cw, ch = canvas_size
    tw = 150  # área do título
    aw = ch - tw
    iw, ih = image.size
    scale = min(cw/iw, aw/ih)
    ns = (int(iw*scale), int(ih*scale))
    try: image = image.resize(ns, Image.Resampling.LANCZOS)
    except: image = image.resize(ns, Image.LANCZOS)
    if image.mode == 'RGBA':
        bg = Image.new('RGB', image.size, (26,26,26)); bg.paste(image, mask=image.split()[3]); image = bg
    elif image.mode != 'RGB':
        image = image.convert('RGB')
    x = (cw - ns[0])//2; y = tw + (aw - ns[1])//2
    canvas.paste(image, (x, y))
    d = ImageDraw.Draw(canvas)
    try:
        main_font = ImageFont.truetype("arial.ttf", 80)
        char_font = ImageFont.truetype("arial.ttf", 50)
    except:
        try:
            main_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 80)
            char_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 50)
        except:
            main_font = ImageFont.load_default(); char_font = ImageFont.load_default()
    bbox = d.textbbox((0,0), text, font=main_font)
    tx = (cw - (bbox[2]-bbox[0]))//2; ty = 20
    for ox in range(-5,6):
        for oy in range(-5,6):
            if ox or oy: d.text((tx+ox, ty+oy), text, font=main_font, fill=(0,0,0))
    d.text((tx, ty), text, font=main_font, fill=(255,255,255))
    if character_name:
        cb = d.textbbox((0,0), character_name, font=char_font)
        cx = (cw - (cb[2]-cb[0]))//2; cy = 110
        for ox in range(-3,4):
            for oy in range(-3,4):
                if ox or oy: d.text((cx+ox, cy+oy), character_name, font=char_font, fill=(0,0,0))
        d.text((cx, cy), character_name, font=char_font, fill=(255,75,75))
    return canvas

# ==================== TRANSIÇÃO (FADE) ====================
def make_same_size(a: Image.Image, b: Image.Image):
    w, h = max(a.width, b.width), max(a.height, b.height)
    def pad(img):
        bg = Image.new("RGB", (w, h), (26,26,26))
        bg.paste(img, ((w-img.width)//2, (h-img.height)//2))
        return bg
    return pad(a), pad(b)

def transition_fade(placeholder, img_from: Image.Image, img_to: Image.Image, duration=0.7, steps=10):
    if img_from is None:
        placeholder.image(img_to, use_container_width=True); return
    a, b = make_same_size(img_from, img_to)
    per = max(duration/steps, 0.02)
    for i in range(steps+1):
        alpha = i/float(steps)
        frame = Image.blend(a, b, alpha)
        placeholder.image(frame, use_container_width=True)
        time.sleep(per)

# ==================== SESSION STATE ====================
ensure_storage()
if "memes_collection" not in st.session_state:
    st.session_state.memes_collection = load_entries_from_disk()
if "current_slide" not in st.session_state:
    st.session_state.current_slide = 0
if "presenter_unlocked" not in st.session_state:
    st.session_state.presenter_unlocked = False
if "autoplay" not in st.session_state:
    st.session_state.autoplay = False

# ==================== SIDEBAR ====================
with st.sidebar:
    st.header("🎉 Modo Festa")
    mode = st.radio("Escolha o Modo:", ["👥 Coleta (Convidados)", "🎬 Apresentação (Host)"])
    st.divider()
    st.metric("Total de Personagens", len(st.session_state.memes_collection))

    # SENHA DO HOST
    if mode == "🎬 Apresentação (Host)":
        pwd = st.text_input("🔒 Senha do Host", type="password", placeholder="2810")
        if st.button("🔑 Entrar como Host", use_container_width=True):
            if pwd == "2810":
                st.session_state.presenter_unlocked = True
                st.success("Acesso liberado! ✅")
            else:
                st.session_state.presenter_unlocked = False
                st.error("Senha incorreta. ❌")

        if st.session_state.presenter_unlocked and len(st.session_state.memes_collection) > 0:
            st.divider()
            if st.button("🗑️ Limpar Todos", type="secondary", use_container_width=True):
                clear_all_disk_data()
                st.session_state.memes_collection = []
                st.session_state.current_slide = 0
                do_rerun()

    st.divider()
    if SERPAPI_KEY:
        st.success("✅ SerpAPI Configurado")
        st.caption(f"Key: {SERPAPI_KEY[:8]}...{SERPAPI_KEY[-4:]}")
    else:
        st.error("❌ API Key não configurada")
    st.divider()
    st.info("🔥 Powered by Google Images (SerpAPI)")

# ==================== MAIN ====================
if mode == "👥 Coleta (Convidados)":
    st.title("🗣️ HEAR ME OUT")
    st.markdown("### Qual personagem você acha atraente? 😏")
    st.markdown("*Seja honesto... ninguém vai julgar (muito)!*")

    col1, col2 = st.columns([3, 1])
    with col1:
        character_name = st.text_input("🎭 Nome do Personagem", placeholder="Ex: Shrek, Pikachu, Megamente...", key="char_input")
        guest_name = st.text_input("👤 Seu Nome (Opcional)", placeholder="Ex: Maria, João...", key="guest_input")
    with col2:
        st.success("✨ **Google Images**")
        st.caption("Encontramos QUALQUER personagem!")
        st.caption("• Shrek\n• Mike Wazowski\n• Lorde Farquaad\n• Megamente")

    if st.button("💕 Adicionar à Lista", type="primary", use_container_width=True):
        if not character_name.strip():
            st.warning("⚠️ Por favor, digite o nome de um personagem!")
        else:
            img, source = fetch_character_image(character_name, SERPAPI_KEY)
            meme = create_meme(img, text="HEAR ME OUT", character_name=character_name)
            save_entry_to_disk(
                character=character_name,
                guest=guest_name.strip() if guest_name else "Anônimo",
                pil_image=meme,
                source=source
            )
            st.session_state.memes_collection = load_entries_from_disk()
            st.success(f"✅ **{character_name}** adicionado à lista!")
            st.balloons()
            st.image(meme, caption=f"Adicionado por: {guest_name or 'Anônimo'}", use_container_width=True)

    st.divider()
    if len(st.session_state.memes_collection) > 0:
        st.subheader(f"📊 {len(st.session_state.memes_collection)} personagens coletados!")
        cols = st.columns(4)
        for idx, m in enumerate(st.session_state.memes_collection[-8:]):
            with cols[idx % 4]:
                st.caption(f"**{m['character']}**")
                st.caption(f"👤 {m['guest']}")
                st.caption(f"🕐 {m['timestamp']}")

else:
    # ==================== APRESENTAÇÃO ====================
    st.session_state.memes_collection = load_entries_from_disk()
    st.title("🎬 Apresentação: HEAR ME OUT da Galera!")

    if not st.session_state.presenter_unlocked:
        st.warning("🔒 Acesso restrito. Informe a senha do host na barra lateral para entrar.")
        st.stop()

    if len(st.session_state.memes_collection) == 0:
        st.warning("⚠️ Nenhum personagem foi adicionado ainda!")
        st.info("👈 Volte para o modo **Coleta** e adicione alguns personagens primeiro!")
        st.stop()

    # ---- atalhos de teclado (setas + espaço) via query params ----
    components.html("""
    <script>
    document.addEventListener('keydown', function(e){
        // evita scroll da página com espaço
        if (e.code === 'Space') { e.preventDefault(); }
        const url = new URL(window.location.href);
        if (e.key === 'ArrowRight') { url.searchParams.set('nav','next'); window.location.href = url.toString(); }
        else if (e.key === 'ArrowLeft') { url.searchParams.set('nav','prev'); window.location.href = url.toString(); }
        else if (e.code === 'Space') { url.searchParams.set('toggle','autoplay'); window.location.href = url.toString(); }
    });
    </script>
    """, height=0)

    # processa query params de navegação
    qp = _get_qparams()
    if qp.get("toggle") == "autoplay":
        st.session_state.autoplay = not st.session_state.autoplay
        _clear_qparams()
        do_rerun()
    if qp.get("nav") == "next":
        st.session_state.current_slide = (st.session_state.current_slide + 1) % len(st.session_state.memes_collection)
        _clear_qparams()
        do_rerun()
    if qp.get("nav") == "prev":
        st.session_state.current_slide = (st.session_state.current_slide - 1) % len(st.session_state.memes_collection)
        _clear_qparams()
        do_rerun()

    # ---- controles ----
    c1, c2, c3, c4, c5 = st.columns([1.3, 1.3, 1.2, 1.6, 1.6])
    with c1:
        trans = st.selectbox("Transição", ["Sem transição", "Fade"], index=1)
    with c2:
        sec = st.slider("Duração por slide (s)", 1.0, 10.0, 3.0, 0.5)
    with c3:
        if not st.session_state.autoplay:
            if st.button("▶️ Iniciar", use_container_width=True):
                st.session_state.autoplay = True
                do_rerun()
        else:
            if st.button("⏹️ Parar", use_container_width=True):
                st.session_state.autoplay = False
                do_rerun()
    with c4:
        if st.button("⛶ Tela cheia", use_container_width=True):
            components.html("""
            <script>
            const d = window.parent.document;
            const el = d.documentElement;
            if (el.requestFullscreen) el.requestFullscreen();
            else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
            else if (el.mozRequestFullScreen) el.mozRequestFullScreen();
            else if (el.msRequestFullscreen) el.msRequestFullscreen();
            </script>
            """, height=0)
    with c5:
        if st.button("❎ Sair da tela cheia", use_container_width=True):
            components.html("""
            <script>
            if (document.fullscreenElement) { document.exitFullscreen(); }
            else if (document.webkitFullscreenElement) { document.webkitCancelFullScreen(); }
            </script>
            """, height=0)

    st.divider()

    # ---- slide atual ----
    cur = st.session_state.memes_collection[st.session_state.current_slide]
    st.markdown(
        f"<h1 style='text-align:center;color:#FF4B4B;font-size:3.2em;margin:0;'>🎭 {cur['character']}</h1>",
        unsafe_allow_html=True
    )
    who = cur.get("guest") or "Anônimo"
    st.markdown(
        f"<h3 style='text-align:center;color:#888;margin-top:0.2rem;'>Enviado por: <span style='color:#FF4B4B;'>{who}</span></h3>",
        unsafe_allow_html=True
    )
    st.markdown(
        f"<p style='text-align:center;color:#999;margin-top:-0.3rem;'>⏰ {cur['timestamp']}</p>",
        unsafe_allow_html=True
    )

    show_area = st.empty()

    # imagem atual e anterior para fade
    try:
        img_current = Image.open(cur['image_path'])
    except Exception:
        img_current = create_placeholder_image(cur['character'])
    prev_idx = (st.session_state.current_slide - 1) % len(st.session_state.memes_collection)
    img_prev = None
    if len(st.session_state.memes_collection) > 1:
        try:
            img_prev = Image.open(st.session_state.memes_collection[prev_idx]['image_path'])
        except Exception:
            img_prev = None

    if trans == "Fade":
        transition_fade(show_area, img_prev, img_current, duration=0.7, steps=10)
    else:
        show_area.image(img_current, use_container_width=True)

    # autoplay
    if st.session_state.autoplay:
        time.sleep(sec)
        st.session_state.current_slide = (st.session_state.current_slide + 1) % len(st.session_state.memes_collection)
        do_rerun()

    st.divider()

    # ---- galeria ----
    st.subheader("📸 Galeria Completa")
    cols = st.columns(5)
    for idx, m in enumerate(st.session_state.memes_collection):
        with cols[idx % 5]:
            try:
                st.image(Image.open(m['image_path']), use_container_width=True)
            except Exception:
                st.caption("Imagem indisponível")
            if st.button(f"{m['character'][:15]}", key=f"thumb_{idx}", use_container_width=True,
                         type="secondary" if idx != st.session_state.current_slide else "primary"):
                st.session_state.current_slide = idx
                do_rerun()
            st.caption(f"👤 {m.get('guest','Anônimo')}")

st.divider()
st.caption("Made with ❤️ for your party | Powered by SerpAPI + Google Images")
