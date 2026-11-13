"""DayZ ping real: la lista de servidores de DZSA con el ping ICMP medido desde este PC.

El ping del launcher mide la consulta A2S, que a veces contesta un filtro anti-DDoS cercano
en vez del servidor; el ICMP llega al servidor de verdad. Al cerrar la ventana el proceso termina.
"""
import ctypes, gzip, json, os, queue, socket, struct, sys, threading, time, urllib.request, winreg
import tkinter as tk
from collections import Counter, namedtuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from ctypes import wintypes
from tkinter import font as tkfont, messagebox, ttk

CACHE = os.path.expandvars(r'%LOCALAPPDATA%\DZSALauncher\data\dayz-servers.json')
URL = 'https://dayzsalauncher.com/api/v1/launcher/servers/dayz'
HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS = os.path.join(HERE, 'settings.json')  # idioma y tema elegidos
HISTORY = os.path.join(HERE, 'history.json')  # jugadores por servidor cada vez que se abre el programa
Server = namedtuple('Server', 'name map players max ip port fpp mods password official modids info')
COLS = {'ping': 90, 'players': 90, 'act': 100, 'name': 400, 'map': 120, 'fpp': 60, 'mods': 60, 'addr': 170}  # ancho
THEMES = {
    'dark': dict(bg='#1e1f22', field='#2b2d31', head='#313338', line='#45474d', fg='#e3e3e3', accent='#5b8def',
                 sel='#35507a', selfg='#ffffff', good='#4ade80', mid='#facc15', bad='#f87171'),
    'light': dict(bg='#f3f3f3', field='#ffffff', head='#e6e6e6', line='#c4c4c4', fg='#1f1f1f', accent='#2f6fd6',
                  sel='#cfe3ff', selfg='#000000', good='#1a7f37', mid='#9a6700', bad='#cf222e'),
}
TEXT = {  # clave: (español, inglés)
    'title': ('DayZ - ping real', 'DayZ - real ping'),
    'search': ('Buscar:', 'Search:'),
    'loading': ('Cargando lista...', 'Loading list...'),
    'map': ('Mapa:', 'Map:'), 'view': ('Vista:', 'View:'), 'mods': ('Mods:', 'Mods:'), 'type': ('Tipo:', 'Type:'),
    'maxping': ('Ping máx:', 'Max ping:'), 'minpl': ('Mín. jugadores:', 'Min. players:'),
    'hidepw': ('Ocultar con contraseña', 'Hide passworded'), 'hidenr': ('Ocultar sin respuesta', 'Hide no response'),
    'all': ('Todos', 'All'),
    'fpp_v': (['Todas', '1PP', '3PP'], ['All', '1PP', '3PP']),
    'mods_v': (['Todos', 'Sin mods', 'Con mods'], ['All', 'No mods', 'Modded']),
    'kind_v': (['Todos', 'Oficiales', 'Comunidad'], ['All', 'Official', 'Community']),
    'act_v': (['Nula', 'Baja', 'Media', 'Alta'], ['None', 'Low', 'Medium', 'High']),
    'light': ('☀ Claro', '☀ Light'), 'dark': ('☾ Oscuro', '☾ Dark'),
    'hint': ('Doble clic: detalles · Clic derecho o F5: refrescar la fila (ping, jugadores…) · Clic en una columna: '
             'ordenar · Shift+clic: añadir otra (Ping y luego Jugadores = menos ping y, en cada tramo de 20 ms, más '
             'llenos) · Actividad: media de jugadores en 7 días, según las veces que abriste el programa '
             '(Alta 30+, Media 10+, Baja 1+)',
             'Double-click: details · Right-click or F5: refresh the row (ping, players…) · Click a column: sort · '
             'Shift+click: add another (Ping then Players = lowest ping and, within each 20 ms band, the fullest) · '
             'Activity: average players over 7 days, from the times you opened the program (High 30+, Medium 10+, '
             'Low 1+)'),
    'm_refresh': ('↻ Refrescar', '↻ Refresh'), 'm_details': ('Detalles', 'Details'),
    'status': ('{} de {} servidores · {} · ping {}/{}', '{} of {} servers · {} · ping {}/{}'),
    'cache': ('lista del launcher', "launcher's list"), 'download': ('lista descargada', 'downloaded list'),
    'measuring': ('midiendo', 'measuring'), 'noresp': ('sin resp.', 'no resp.'),
    'col_ping': ('Ping real', 'Real ping'), 'col_players': ('Jugadores', 'Players'), 'col_act': ('Actividad', 'Activity'),
    'col_name': ('Nombre', 'Name'), 'col_map': ('Mapa', 'Map'), 'col_fpp': ('Vista', 'View'),
    'col_mods': ('Mods', 'Mods'), 'col_addr': ('IP:puerto', 'IP:port'),
    'd_addr': ('Dirección', 'Address'), 'd_qport': ('puerto de consulta', 'query port'),
    'd_nonames': ('DayZ no comparte los nombres', "DayZ doesn't share names"),
    'official': ('Oficial', 'Official'), 'community': ('Comunidad', 'Community'),
    'd_pw': ('Contraseña', 'Password'), 'yes': ('Sí', 'Yes'), 'no': ('No', 'No'),
    'd_version': ('Versión', 'Version'), 'd_time': ('Hora en el juego', 'In-game time'),
    'd_accel': ('el tiempo va x{}', 'time runs x{}'), 'd_copy': ('Copiar IP:puerto', 'Copy IP:port'),
    'd_mods': ('Mods ({}) · doble clic abre su página en Steam', 'Mods ({}) · double-click opens its Steam page'),
    'd_nomods': ('Sin mods', 'No mods'), 'd_wid': ('ID del Workshop', 'Workshop ID'),
    'd_chart': ('Jugadores por día: media y pico, según las {} veces que abriste el programa en 7 días',
                'Players per day: average and peak, from the {} times you opened the program in 7 days'),
    'd_nodata': ('Aún no hay historial: se guarda cada vez que abres el programa.',
                 'No history yet: it is saved each time you open the program.'),
    'd_avg': ('media', 'average'), 'd_peak': ('pico', 'peak'),
    'days': (['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'], ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']),
    'ch_btn': ('Borrar historial ({})', 'Clear history ({})'), 'ch_title': ('Borrar historial', 'Clear history'),
    'ch_ask': ('¿Borrar el historial de jugadores ({})?\n\nLa columna Actividad y las gráficas de los detalles '
               'empezarán de cero.',
               'Delete the player history ({})?\n\nThe Activity column and the detail charts will start from zero.'),
    'modpick': ('Elegir mods…', 'Pick mods…'), 'mp_title': ('Filtrar por mods', 'Filter by mods'),
    'mp_hint': ('Elige uno o varios (Ctrl/Shift+clic) y pulsa un botón. Exigido: el servidor tiene que tenerlos '
                'todos. Excluido: no puede tener ninguno.',
                "Pick one or more (Ctrl/Shift+click) and press a button. Required: the server must have all of them. "
                "Excluded: it can't have any."),
    'mp_req': ('✔ Exigir', '✔ Require'), 'mp_exc': ('✖ Excluir', '✖ Exclude'),
    'mp_unset': ('Quitar', 'Unset'), 'mp_clear': ('Limpiar todo', 'Clear all'),
    'mp_is_req': ('✔ exigido', '✔ required'), 'mp_is_exc': ('✖ excluido', '✖ excluded'),
    'mp_state': ('Estado', 'State'), 'mp_servers': ('Servidores', 'Servers'),
}

icmp = ctypes.windll.iphlpapi
icmp.IcmpCreateFile.restype = wintypes.HANDLE
icmp.IcmpSendEcho.argtypes = [wintypes.HANDLE, wintypes.ULONG, ctypes.c_void_p, wintypes.WORD,
                              ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD]
_local = threading.local()


def ping(ip, timeout_ms=1000):
    """RTT ICMP en ms, o None si no responde (un 20 % de servidores bloquea el ping)."""
    if not hasattr(_local, 'h'):
        _local.h = icmp.IcmpCreateFile()  # un handle por hilo
    addr = struct.unpack('<I', socket.inet_aton(ip))[0]
    buf = ctypes.create_string_buffer(128)
    if not icmp.IcmpSendEcho(_local.h, addr, b'dayzping', 8, None, buf, len(buf), timeout_ms):
        return None
    status, rtt = struct.unpack_from('<II', buf, 4)  # ICMP_ECHO_REPLY.Status, .RoundTripTime
    return rtt if status == 0 else None


def fetch_json(url, timeout):
    """GET a la API de DZSA: se identifica con el nombre y la web del programa y pide la respuesta comprimida."""
    req = urllib.request.Request(url, headers={
        'User-Agent': 'dayz-real-ping-browser/1.0 (+https://github.com/pepperoniego1247/dayz-real-ping-browser)',
        'Accept-Encoding': 'gzip'})  # la lista pasa de ~15 MB a ~2,4 MB
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        return json.loads(gzip.decompress(body) if r.headers.get('Content-Encoding') == 'gzip' else body)


def mod_key(m):
    return str(m.get('steamWorkshopId') or m.get('name'))  # el ID: el nombre cambia de un servidor a otro


def load_servers():
    """Servidores con jugadores como [Server], de dónde salió la lista ('cache' o 'download') y de cuándo es."""
    data = None
    if not (os.path.exists(CACHE) and time.time() - os.path.getmtime(CACHE) < 1800):
        try:  # la caché del launcher tiene más de 30 min: jugadores desactualizados
            data, src, ts = fetch_json(URL, 60), 'download', time.time()
        except OSError:
            if not os.path.exists(CACHE):
                raise
    if data is None:
        with open(CACHE, encoding='utf-8') as f:
            data, src, ts = json.load(f), 'cache', os.path.getmtime(CACHE)
    if isinstance(data, dict):  # la API envuelve en {"result": [...]}, la caché del launcher no
        data = data['result']
    return [make_server(s) for s in data if s['players'] > 0], src, ts


def make_server(s):
    return Server(s['name'], s['map'], s['players'], s['maxPlayers'], s['endpoint']['ip'], s['gamePort'],
                  '1PP' if s.get('firstPersonOnly') else '3PP', len(s.get('mods') or ()), bool(s.get('password')),
                  s.get('shard') == 'public',  # oficiales = shard "public", comunidad = "private"
                  frozenset(mod_key(m) for m in s.get('mods') or ()), s)


def query_server(ip, qport):
    """Datos frescos de un solo servidor (mismos campos que la lista, <1 KB) desde la API de DZSA."""
    res = fetch_json(f'https://dayzsalauncher.com/api/v1/query/{ip}/{qport}', 15).get('result')
    if not isinstance(res, dict) or 'endpoint' not in res:
        raise ValueError('DZSA no pudo consultar el servidor')
    return res


def update_history(rows, ts, path=HISTORY, keep_days=8):
    """Añade una foto [hora, {ip:puerto: jugadores}] al historial (borra lo de más de 8 días) y lo devuelve.

    Solo se llama al abrir el programa: no hay nada en segundo plano, así que el historial tiene los huecos
    de cuando no se abrió. Los servidores vacíos no se guardan (cuentan como 0).
    """
    try:
        with open(path, encoding='utf-8') as f:
            hist = json.load(f)
    except (OSError, ValueError):
        hist = []
    hist = [h for h in hist if h[0] > ts - keep_days * 86400]
    if not hist or ts - hist[-1][0] > 1200:  # reabrir con la misma lista (<20 min) no cuenta doble
        hist.append([ts, {f'{s.ip}:{s.port}': s.players for s in rows}])
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(hist, f, separators=(',', ':'))
        except OSError:
            pass  # sin permiso de escritura: el historial de esta vez no se guarda
    return hist


def avg_players(hist, key, now, min_snaps=3):
    """Media de jugadores en los últimos 7 días, o None si hay menos de 3 fotos (no sería fiable)."""
    week = [h[1] for h in hist if h[0] > now - 7 * 86400]
    return sum(h.get(key, 0) for h in week) / len(week) if len(week) >= min_snaps else None


def act_level(avg):
    return 3 if avg >= 30 else 2 if avg >= 10 else 1 if avg >= 1 else 0  # índice de 'act_v'


def size_text(path):
    try:
        n = os.path.getsize(path)
    except OSError:
        n = 0
    return f'{n / 1048576:.1f} MB' if n >= 1048576 else f'{n // 1024} KB'


def tag(ms):
    return '' if ms == '' else 'bad' if ms is None or ms >= 170 else 'mid' if ms >= 100 else 'good'


def num(var):
    try:
        return int(var.get())
    except ValueError:
        return None


def windows_dark():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as k:
            return winreg.QueryValueEx(k, 'AppsUseLightTheme')[0] == 0
    except OSError:
        return True


class App:
    def __init__(self, root):
        self.root, self.q, self.ms, self.rows, self.by_ip = root, queue.Queue(), {}, [], {}
        self.sort, self.src, self.total, self.shown, self.done = [('players', True)], '', 0, 0, False
        self.maps, self.modlist, self.req, self.exc, self.picker, self.i18n = [], [], set(), set(), None, []
        self.hist, self.act, self.subwins, self.refreshing = [], {}, {}, set()
        self.refresh_pool = ThreadPoolExecutor(4)  # F5 con muchas filas: como mucho 4 consultas a DZSA a la vez
        try:
            with open(SETTINGS, encoding='utf-8') as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            cfg = {}
        # sin elección guardada: el tema de Windows y español (el idioma se cambia con ES | EN y se recuerda)
        self.theme = cfg.get('theme') if cfg.get('theme') in THEMES else 'dark' if windows_dark() else 'light'
        self.lang = tk.StringVar(value='en' if cfg.get('lang') == 'en' else 'es')
        self.k = k = root.winfo_fpixels('1i') / 96  # escala para pantallas con zoom
        root.geometry(f'{int(1180 * k)}x{int(650 * k)}')  # lo justo para la fila de filtros
        root.protocol('WM_DELETE_WINDOW', lambda: os._exit(0))  # corta también los hilos de ping
        self.icon_font = tkfont.nametofont('TkDefaultFont').copy()  # guardada: si no, Tk la borra
        self.icon_font.configure(size=self.icon_font.cget('size') + 3)

        def var(cls=tk.StringVar, value=''):
            v = cls(value=value)
            v.trace_add('write', lambda *_: self.render())
            return v
        self.search, self.max_ping, self.min_players = var(), var(), var()
        self.hide_pw, self.hide_noresp = var(tk.BooleanVar, True), var(tk.BooleanVar, True)

        top = ttk.Frame(root, padding=(8, 6))
        top.pack(fill='x')
        self.txt(ttk.Label(top), 'search').pack(side='left')
        entry = ttk.Entry(top, textvariable=self.search, width=36)
        entry.pack(side='left', padx=6)
        entry.focus()
        self.mods_btn = ttk.Button(top, command=self.mod_picker)
        self.mods_btn.pack(side='left', padx=6)
        self.hist_btn = ttk.Button(top, command=self.clear_history)
        self.hist_btn.pack(side='left')
        for code in ('en', 'es'):  # se apilan desde la derecha: queda [ES][EN]
            ttk.Radiobutton(top, text=code.upper(), value=code, variable=self.lang, style='Toolbutton',
                            command=lambda: (self.retranslate(), self.refresh_subwins(), self.save_settings())
                            ).pack(side='right')
        self.theme_btn = ttk.Button(top, command=self.toggle_theme)
        self.theme_btn.pack(side='right', padx=8)
        self.status = ttk.Label(top)
        self.status.pack(side='right', padx=10)

        bar = ttk.Frame(root, padding=(8, 0, 8, 6))
        bar.pack(fill='x')

        def labeled(key, widget):
            self.txt(ttk.Label(bar), key).pack(side='left', padx=(0, 4))
            widget.pack(side='left', padx=(0, 12))
            return widget
        self.combos = tuple(labeled(key, ttk.Combobox(bar, state='readonly', width=w))
                            for key, w in (('map', 14), ('view', 6), ('mods', 9), ('type', 10)))
        for cb in self.combos:
            cb.bind('<<ComboboxSelected>>', lambda e: self.render())
        labeled('maxping', ttk.Spinbox(bar, textvariable=self.max_ping, from_=0, to=500, increment=10, width=5))
        labeled('minpl', ttk.Spinbox(bar, textvariable=self.min_players, from_=0, to=127, increment=5, width=5))
        self.txt(ttk.Checkbutton(bar, variable=self.hide_pw), 'hidepw').pack(side='left', padx=(0, 12))
        self.txt(ttk.Checkbutton(bar, variable=self.hide_noresp), 'hidenr').pack(side='left')

        self.txt(ttk.Label(root, padding=(8, 3), wraplength=int(1160 * k)), 'hint').pack(side='bottom', fill='x')
        self.tree = ttk.Treeview(root, columns=list(COLS), show='headings')
        for c, w in COLS.items():
            self.tree.heading(c, command=lambda c=c: self.sort_by(c))
            self.tree.column(c, width=int(w * k), stretch=c == 'name',
                             anchor='w' if c in ('name', 'map') else 'center')
        self.tree.bind('<Shift-Button-1>', self.shift_click)
        self.tree.bind('<Double-1>', lambda e: self.tree.identify_region(e.x, e.y) == 'cell'
                       and self.details(self.tree.identify_row(e.y)))
        self.tree.bind('<Return>', lambda e: self.details(self.tree.focus()))
        self.tree.bind('<Button-3>', self.row_menu)
        self.tree.bind('<F5>', lambda e: self.refresh_selected())
        scroll = ttk.Scrollbar(root, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)

        self.rowh = tkfont.nametofont('TkDefaultFont').metrics('linespace') + int(6 * k)
        self.retranslate()
        self.apply_theme()
        threading.Thread(target=self.work, daemon=True).start()
        root.after(200, self.poll)

    # --- idioma ---
    def t(self, key):
        return TEXT[key][self.lang.get() == 'en']

    def txt(self, widget, key):
        """Registra un widget cuyo texto cambia con el idioma."""
        self.i18n.append((widget, key))
        return widget

    def fmt(self, ms):
        return self.t('measuring') if ms == '' else self.t('noresp') if ms is None else f'{ms} ms'

    def fmt_act(self, s):
        avg = self.act.get(f'{s.ip}:{s.port}')
        return '—' if avg is None else f"{self.t('act_v')[act_level(avg)]} · {avg:.0f}"

    def retranslate(self):
        self.root.title(self.t('title'))
        for w, key in self.i18n:
            w.config(text=self.t(key))
        for cb, values in zip(self.combos, ([self.t('all')] + self.maps, self.t('fpp_v'), self.t('mods_v'),
                                            self.t('kind_v'))):
            i = max(cb.current(), 0)  # se guarda la opción elegida por posición, no por texto
            cb['values'] = values
            cb.current(i)
        self.theme_btn.config(text=self.t('light' if self.theme == 'dark' else 'dark'))
        self.update_mods_btn()
        self.hist_btn.config(text=self.t('ch_btn').format(size_text(HISTORY)))
        self.render()
        self.update_status()

    def clear_history(self):
        if not messagebox.askyesno(self.t('ch_title'), self.t('ch_ask').format(size_text(HISTORY)), parent=self.root):
            return
        try:
            os.remove(HISTORY)
        except FileNotFoundError:
            pass
        except OSError as e:
            messagebox.showerror(self.t('ch_title'), str(e), parent=self.root)
            return
        self.hist, self.act = [], {}
        self.retranslate()  # actualiza el tamaño del botón y vacía la columna Actividad
        self.refresh_subwins()  # y las gráficas de los detalles abiertos

    def update_status(self):
        self.status.config(text=self.t('status').format(self.shown, len(self.rows), self.t(self.src), len(self.ms),
                                                        self.total) if self.rows else self.t('loading'))

    def save_settings(self):
        try:
            with open(SETTINGS, 'w', encoding='utf-8') as f:
                json.dump({'lang': self.lang.get(), 'theme': self.theme}, f)
        except OSError:
            pass  # sin permiso de escritura: solo se pierde la preferencia

    def update_mods_btn(self):
        n = f' (✔{len(self.req)} ✖{len(self.exc)})' if self.req or self.exc else ''
        self.mods_btn.config(text=self.t('modpick') + n)

    # --- tema ---
    def apply_theme(self):
        c, s = THEMES[self.theme], ttk.Style()
        s.theme_use('clam')  # el tema nativo de Windows no deja cambiar colores
        s.configure('.', background=c['bg'], foreground=c['fg'], fieldbackground=c['field'], bordercolor=c['line'],
                    lightcolor=c['bg'], darkcolor=c['bg'], troughcolor=c['bg'], arrowcolor=c['fg'],
                    insertcolor=c['fg'], selectbackground=c['sel'], selectforeground=c['selfg'],
                    indicatorbackground=c['field'], indicatorforeground=c['fg'])
        # clam trae colores propios por control (casillas blancas, flechas claras al pasar el ratón): pisarlos
        for st in ('TCombobox', 'TSpinbox', 'TScrollbar', 'TButton'):
            s.map(st, background=[('pressed', c['line']), ('active', c['head'])])
        s.map('TCombobox', fieldbackground=[('readonly', c['field'])], foreground=[('readonly', c['fg'])],
              selectbackground=[('readonly', c['field'])], selectforeground=[('readonly', c['fg'])])
        s.configure('TCheckbutton', indicatorbackground=c['field'], indicatorforeground=c['fg'])
        s.map('TCheckbutton', background=[('active', c['bg'])], indicatorbackground=[('pressed', c['line'])])
        s.configure('TButton', background=c['head'])
        s.configure('Toolbutton', background=c['head'], padding=(8, 2))
        s.map('Toolbutton', background=[('selected', c['sel']), ('active', c['line'])],
              foreground=[('selected', c['selfg'])])
        s.configure('Icon.Toolbutton', background=c['bg'], padding=(3, 0), font=self.icon_font)  # botón-icono plano
        s.map('Icon.Toolbutton', background=[('active', c['head'])], foreground=[('disabled', c['line'])])
        s.configure('Treeview', background=c['field'], fieldbackground=c['field'], rowheight=self.rowh)
        s.map('Treeview', background=[('selected', c['sel'])], foreground=[('selected', c['selfg'])])
        s.configure('Treeview.Heading', background=c['head'], padding=4)
        s.map('Treeview.Heading', background=[('active', c['line'])])
        for t in ('good', 'mid', 'bad'):
            self.tree.tag_configure(t, foreground=c[t])
        for cb in self.combos:  # la lista desplegable es un widget clásico: el estilo ttk no la pinta
            pd = self.root.tk.call('ttk::combobox::PopdownWindow', cb)
            self.root.tk.call(f'{pd}.f.l', 'configure', '-background', c['field'], '-foreground', c['fg'],
                              '-selectbackground', c['sel'], '-selectforeground', c['selfg'])
        self.theme_btn.config(text=self.t('light' if self.theme == 'dark' else 'dark'))
        self.paint(self.root)  # las ventanas secundarias se repintan al reconstruirse (refresh_subwins)

    def paint(self, win):
        win.configure(bg=THEMES[self.theme]['bg'])
        win.update_idletasks()
        try:  # barra de título oscura (Windows 11) y repintarla ya
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(self.theme == 'dark')), 4)
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x27)  # FRAMECHANGED|NOMOVE|NOSIZE|NOZORDER
        except OSError:
            pass

    def toggle_theme(self):
        self.theme = 'light' if self.theme == 'dark' else 'dark'
        self.apply_theme()
        self.refresh_subwins()
        self.save_settings()

    # --- ventanas secundarias: se reconstruyen solas (tema, idioma, historial) sin perder su estado ---
    def subwindow(self, geometry, build):
        """Ventana cuyo contenido dibuja build(win, frame), que devuelve save(): guarda scroll, selección...

        refresh_subwins llama a save(), tira el contenido y lo vuelve a dibujar en la misma ventana,
        así que la posición y el tamaño no cambian.
        """
        win = tk.Toplevel(self.root)
        win.geometry(geometry)
        cur = {'frm': None, 'save': None}

        def rebuild():
            if cur['frm']:
                cur['save']()
                cur['frm'].destroy()
            cur['frm'] = frm = ttk.Frame(win, padding=10)
            frm.pack(fill='both', expand=True)
            cur['save'] = build(win, frm)
            self.paint(win)
        self.subwins[win] = rebuild
        rebuild()
        return win

    def refresh_subwins(self):
        for win, rebuild in list(self.subwins.items()):
            if win.winfo_exists():
                rebuild()
            else:
                del self.subwins[win]

    def mod_picker(self):
        """Lista de todos los mods distintos de los servidores con jugadores, para exigirlos o excluirlos."""
        if self.picker and self.picker.winfo_exists():
            self.picker.lift()
            return
        k, q, st, w = self.k, tk.StringVar(), {'sel': (), 'y': 0.0, 'first': True}, {}  # st/q sobreviven
        q.trace_add('write', lambda *_: w['fill']())

        def build(win, frm):
            t = self.t
            win.title(t('mp_title'))
            row = ttk.Frame(frm)
            row.pack(fill='x')
            ttk.Label(row, text=t('search')).pack(side='left')
            e = ttk.Entry(row, textvariable=q, width=34)
            e.pack(side='left', padx=6)
            if st['first']:  # al reconstruir no le quita el foco a la ventana principal
                e.focus()
                st['first'] = False
            ttk.Label(frm, text=t('mp_hint'), wraplength=int(590 * k)).pack(anchor='w', pady=6)
            btns = ttk.Frame(frm)
            btns.pack(side='bottom', fill='x', pady=(8, 0))
            box = ttk.Frame(frm)
            box.pack(fill='both', expand=True)
            tree = ttk.Treeview(box, columns=('state', 'name', 'servers', 'id'), show='headings')
            for c, head, wd in (('state', t('mp_state'), 100), ('name', 'Mod', 270),
                                ('servers', t('mp_servers'), 90), ('id', t('d_wid'), 140)):
                tree.heading(c, text=head)
                tree.column(c, width=int(wd * k), stretch=c == 'name', anchor='w' if c == 'name' else 'center')
            for tg in ('good', 'bad'):
                tree.tag_configure(tg, foreground=THEMES[self.theme][tg])
            sb = ttk.Scrollbar(box, command=tree.yview)
            tree.configure(yscrollcommand=sb.set)
            sb.pack(side='right', fill='y')
            tree.pack(fill='both', expand=True)

            def state(key):
                return ((t('mp_is_req'), 'good') if key in self.req else
                        (t('mp_is_exc'), 'bad') if key in self.exc else ('', ''))

            def fill():
                text = q.get().lower()
                tree.delete(*tree.get_children())
                active = lambda m: m[0] not in self.req and m[0] not in self.exc  # los elegidos arriba
                for key, name, n in sorted(self.modlist, key=active):
                    if text in name.lower() or text in key:
                        label, tg = state(key)
                        tree.insert('', 'end', iid=key, values=(label, name, n, key), tags=(tg,))

            def mark(target):
                for key in tree.selection():
                    self.req.discard(key)
                    self.exc.discard(key)
                    if target is not None:
                        target.add(key)
                    label, tg = state(key)
                    tree.set(key, 'state', label)
                    tree.item(key, tags=(tg,))
                self.update_mods_btn()
                self.render()

            def clear():
                self.req.clear()
                self.exc.clear()
                fill()
                self.update_mods_btn()
                self.render()
            for key, cmd in (('mp_req', lambda: mark(self.req)), ('mp_exc', lambda: mark(self.exc)),
                             ('mp_unset', lambda: mark(None))):
                ttk.Button(btns, text=t(key), command=cmd).pack(side='left', padx=(0, 6))
            ttk.Button(btns, text=t('mp_clear'), command=clear).pack(side='right')
            w['fill'] = fill
            fill()
            tree.selection_set([x for x in st['sel'] if tree.exists(x)])
            tree.update_idletasks()  # ya, no diferido: dos reconstrucciones seguidas perderían el scroll
            tree.yview_moveto(st['y'])

            def save():
                st['sel'], st['y'] = tree.selection(), tree.yview()[0]
            return save
        self.picker = self.subwindow(f'{int(620 * k)}x{int(640 * k)}', build)

    def details(self, iid):
        """Ventana con los datos del servidor, su ping real (refrescable), jugadores por día y sus mods."""
        if not iid:
            return
        i, k = int(iid), self.k
        st = {'mods_y': 0.0}  # sobrevive a las reconstrucciones

        def build(win, frm):
            t, s = self.t, self.rows[i]  # la versión actual: refrescar el servidor la cambia
            d, qport, mods = s.info, s.info['endpoint']['port'], s.info.get('mods') or []
            win.title(s.name)
            title_font = tkfont.nametofont('TkDefaultFont').copy()
            title_font.configure(weight='bold', size=title_font.cget('size') + 2)
            lbl = ttk.Label(frm, text=s.name, font=title_font, wraplength=int(610 * k))
            lbl.font = title_font  # que la fuente viva lo que viva la etiqueta
            lbl.pack(anchor='w')

            grid = ttk.Frame(frm)
            grid.pack(fill='x', pady=8)
            ping_row = ttk.Frame(grid)  # el ping real con su botón-icono al lado
            busy = i in self.refreshing
            ttk.Label(ping_row, text=self.fmt('' if busy else self.ms.get(s.ip, ''))).pack(side='left')
            btn = ttk.Button(ping_row, text='↻', style='Icon.Toolbutton', command=lambda: self.refresh_server(i))
            btn.pack(side='left', padx=(6, 0))
            if busy:
                btn.state(['disabled'])  # sin cooldown: solo desactivado mientras pide los datos
            yes_no = lambda v: t('yes') if v else t('no')
            info = [(t('d_addr'), f"{s.ip}:{s.port}   ({t('d_qport')} {qport})"), (t('col_map'), s.map),
                    (t('col_players'), f"{s.players}/{s.max}   ({t('d_nonames')})"), (t('col_ping'), ping_row),
                    (t('col_act'), self.fmt_act(s)),
                    (t('col_fpp'), s.fpp), (t('type').rstrip(':'), t('official') if s.official else t('community')),
                    (t('d_pw'), yes_no(s.password)), ('BattlEye', yes_no(d.get('battlEye'))),
                    (t('d_version'), d.get('version', '?')),
                    (t('d_time'), f"{d.get('time', '?')}   ({t('d_accel').format(d.get('timeAcceleration', 1))})")]
            for r, (name, val) in enumerate(info):
                ttk.Label(grid, text=name + ':').grid(row=r, column=0, sticky='w', padx=(0, 12))
                (val if isinstance(val, tk.Widget) else ttk.Label(grid, text=val)).grid(row=r, column=1, sticky='w')

            def copy():
                self.root.clipboard_clear()
                self.root.clipboard_append(f'{s.ip}:{s.port}')
            ttk.Button(frm, text=t('d_copy'), command=copy).pack(anchor='w')
            self.week_chart(frm, f'{s.ip}:{s.port}')

            ttk.Label(frm, text=t('d_mods').format(len(mods)) if mods else t('d_nomods')).pack(anchor='w', pady=(12, 4))
            if not mods:
                return lambda: None
            box = ttk.Frame(frm)
            box.pack(fill='both', expand=True)
            mt = ttk.Treeview(box, columns=('name', 'id'), show='headings')
            mt.heading('name', text='Mod')
            mt.heading('id', text=t('d_wid'))
            mt.column('name', width=int(420 * k), stretch=True)
            mt.column('id', width=int(130 * k), anchor='center')
            for m in mods:
                mt.insert('', 'end', values=(m.get('name', '?'), m.get('steamWorkshopId', '')))
            sb = ttk.Scrollbar(box, command=mt.yview)
            mt.configure(yscrollcommand=sb.set)
            sb.pack(side='right', fill='y')
            mt.pack(fill='both', expand=True)
            mt.update_idletasks()  # ya, no diferido: dos reconstrucciones seguidas perderían el scroll
            mt.yview_moveto(st['mods_y'])

            def open_mod(e):
                row = mt.identify_row(e.y)
                if row and mt.set(row, 'id'):
                    os.startfile(f"steam://url/CommunityFilePage/{mt.set(row, 'id')}")
            mt.bind('<Double-1>', open_mod)

            def save():
                st['mods_y'] = mt.yview()[0]
            return save

        win = self.subwindow(f'{int(640 * k)}x{int(740 * k)}', build)
        win.server = i  # para reconstruirla cuando se refresque este servidor
        self.refresh_server(i)  # datos y ping frescos al abrir

    # --- refrescar un servidor suelto ---
    def refresh_server(self, i):
        """Pide de nuevo un servidor a DZSA (jugadores, hora, mods...) y su ping; actualiza su fila y sus detalles."""
        if i in self.refreshing:
            return
        self.refreshing.add(i)
        s = self.rows[i]
        self.redraw_server(i)

        def work():
            ms = ping(s.ip)
            try:
                info = query_server(s.ip, s.info['endpoint']['port'])
            except (OSError, ValueError):
                info = None  # DZSA no contestó: se quedan los datos que había, pero el ping sí se actualiza

            def done():
                self.refreshing.discard(i)
                if info:
                    self.rows[i] = make_server(info)
                self.redraw_server(i)
            self.q.put(('ping', s.ip, ms))  # también las otras filas con la misma IP
            self.q.put(('call', done))
        self.refresh_pool.submit(work)

    def refresh_selected(self):
        for iid in self.tree.selection():
            self.refresh_server(int(iid))

    def redraw_server(self, i):
        s, iid = self.rows[i], str(i)
        ms = '' if i in self.refreshing else self.ms.get(s.ip, '')
        if self.tree.exists(iid):
            self.tree.item(iid, values=self.row_values(s, ms), tags=(tag(ms),))
        for win, rebuild in list(self.subwins.items()):
            if getattr(win, 'server', None) == i and win.winfo_exists():
                rebuild()

    def row_values(self, s, ms):
        return (self.fmt(ms), f'{s.players}/{s.max}', self.fmt_act(s), s.name, s.map, s.fpp, s.mods,
                f'{s.ip}:{s.port}')

    def row_menu(self, e):
        iid = self.tree.identify_row(e.y)
        if not iid:
            return
        if iid not in self.tree.selection():
            self.tree.selection_set(iid)
        c = THEMES[self.theme]  # el menú se crea cada vez: así sale con el tema e idioma actuales
        m = tk.Menu(self.root, tearoff=0, bg=c['field'], fg=c['fg'], activebackground=c['sel'],
                    activeforeground=c['selfg'])
        m.add_command(label=self.t('m_refresh') + '   F5', command=self.refresh_selected)
        m.add_command(label=self.t('m_details'), command=lambda: self.details(iid))
        m.tk_popup(e.x_root, e.y_root)

    def week_chart(self, parent, key):
        """Barras de los últimos 7 días con el historial propio: pico (gris) y media (color) de cada día."""
        c, k, t, now = THEMES[self.theme], self.k, self.t, time.time()
        days = []
        for back in range(6, -1, -1):
            day = time.localtime(now - back * 86400)
            vals = [h[1].get(key, 0) for h in self.hist if time.localtime(h[0])[:3] == day[:3]]
            days.append((day, sum(vals) / len(vals) if vals else None, max(vals) if vals else None))
        n = sum(1 for h in self.hist if h[0] > now - 7 * 86400)
        ttk.Label(parent, text=t('d_chart').format(n) if n else t('d_nodata')).pack(anchor='w', pady=(12, 4))
        if not n:
            return
        w, h, pad, head = int(610 * k), int(150 * k), int(20 * k), int(38 * k)  # head: leyenda + cifra de arriba
        cv = tk.Canvas(parent, width=w, height=h, bg=c['field'], highlightthickness=0)
        cv.pack(anchor='w')
        top, base, slot = max([p for _, _, p in days if p] + [1]), h - pad, (w - 2 * pad) / 7
        y = lambda v: base - (base - head) * v / top
        for i, (day, avg, peak) in enumerate(days):
            x0, x1 = pad + i * slot + slot * 0.2, pad + (i + 1) * slot - slot * 0.2
            for v, color in ((peak, c['line']), (avg, c['accent'])):
                if v:
                    cv.create_rectangle(x0, y(v), x1, base, fill=color, width=0)
            label = '—' if avg is None else f'{avg:.0f} / {peak}'
            cv.create_text((x0 + x1) / 2, y(peak or 0) - 2, text=label, anchor='s', fill=c['fg'])
            cv.create_text((x0 + x1) / 2, base + 2, text=f"{t('days')[day.tm_wday]} {day.tm_mday}", anchor='n',
                           fill=c['fg'])
        cv.create_text(w - 4, 2, anchor='ne', text=f"■ {t('d_peak')}", fill=c['line'])
        cv.create_text(w - int(60 * k), 2, anchor='ne', text=f"■ {t('d_avg')}", fill=c['accent'])

    # --- datos ---
    def work(self):
        try:
            rows, src, ts = load_servers()
            hist = update_history(rows, ts)
        except Exception as e:
            self.q.put(('error', str(e)))
            return
        self.q.put(('rows', rows, src, hist))
        players = Counter()
        for s in rows:
            players[s.ip] += s.players
        with ThreadPoolExecutor(16) as ex:  # medido: con 32+ a la vez se pierden respuestas por el camino
            futs = {ex.submit(ping, ip): ip for ip, _ in players.most_common()}  # los más llenos primero
            for f in as_completed(futs):
                self.q.put(('ping', futs[f], f.result()))

    def set_rows(self, rows, src, hist):
        self.rows, self.src, self.hist = rows, src, hist
        self.total = len({s.ip for s in rows})
        self.maps = [m for m, _ in Counter(s.map for s in rows).most_common()]
        now = time.time()
        self.act = {key: avg for key in (f'{s.ip}:{s.port}' for s in rows)
                    if (avg := avg_players(hist, key, now)) is not None}
        names, used = {}, Counter()  # SELECT DISTINCT de mods: en cuántos servidores está cada uno
        for s in rows:
            used.update(s.modids)
            for m in s.info.get('mods') or ():
                names.setdefault(mod_key(m), Counter())[m.get('name', '?')] += 1
        self.modlist = [(key, names[key].most_common(1)[0][0], n) for key, n in used.most_common()]
        self.retranslate()  # rellena el desplegable de mapas y dibuja la lista

    def poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == 'error':
                    self.status.config(text=f'Error: {msg[1]}')
                elif msg[0] == 'call':  # algo que un hilo quiere hacer en la ventana (Tk no es seguro entre hilos)
                    msg[1]()
                elif msg[0] == 'rows':
                    self.set_rows(*msg[1:])
                else:
                    _, ip, ms = msg
                    self.ms[ip] = ms
                    for iid in self.by_ip.get(ip, ()):
                        self.tree.set(iid, 'ping', self.fmt(ms))
                        self.tree.item(iid, tags=(tag(ms),))
        except queue.Empty:
            pass
        if self.rows and not self.done and len(self.ms) >= self.total:
            self.done = True  # los filtros de ping dejaron pasar los que aún medían: volver a filtrar
            if any(c == 'ping' for c, _ in self.sort) or num(self.max_ping) or self.hide_noresp.get():
                self.render()
        self.update_status()
        self.root.after(200, self.poll)

    def sort_by(self, col, add=False):
        """Clic: ordenar solo por col (otra vez invierte). Shift+clic: añadirla como siguiente criterio."""
        dirs = dict(self.sort)
        rev = not dirs[col] if col in dirs else col in ('players', 'act', 'mods')  # números grandes primero
        if add and col in dirs:
            self.sort = [(c, rev if c == col else r) for c, r in self.sort]
        elif add:
            self.sort = self.sort + [(col, rev)]
        else:
            self.sort = [(col, rev)]
        self.render()

    def shift_click(self, e):
        if self.tree.identify_region(e.x, e.y) != 'heading':
            return None  # Shift+clic en filas: selección normal
        self.sort_by(list(COLS)[int(self.tree.identify_column(e.x)[1:]) - 1], add=True)
        return 'break'  # que no salte además el clic normal de la cabecera

    def render(self):
        if not self.rows:
            return
        text = self.search.get().lower()
        mapa, fpp, modded, kind = (cb.current() for cb in self.combos)  # 0 = todos
        mapa = self.combos[0].get() if mapa > 0 else None
        fpp = (None, '1PP', '3PP')[max(fpp, 0)]
        max_ping, min_pl = num(self.max_ping), num(self.min_players) or 0
        hide_pw, hide_nr, req, exc = self.hide_pw.get(), self.hide_noresp.get(), self.req, self.exc

        def keep(s):
            ms = self.ms.get(s.ip, '')  # '' = aún midiendo, None = no responde
            return ((text in s.name.lower() or text in s.map.lower())
                    and mapa in (None, s.map) and fpp in (None, s.fpp)
                    and modded in (0, 1 if s.mods == 0 else 2)
                    and kind in (0, 1 if s.official else 2)
                    and req <= s.modids and not exc & s.modids
                    and s.players >= min_pl and not (hide_pw and s.password)
                    and not (hide_nr and ms is None)
                    and not (max_ping and (ms is None or (ms != '' and ms > max_ping))))

        def ping_key(s):
            ms = self.ms.get(s.ip)
            return 99999 if ms is None else ms
        keys = {'ping': ping_key, 'players': lambda s: s.players, 'act': lambda s: self.act.get(f'{s.ip}:{s.port}', -1),
                'name': lambda s: s.name.lower(), 'map': lambda s: s.map.lower(), 'fpp': lambda s: s.fpp,
                'mods': lambda s: s.mods, 'addr': lambda s: socket.inet_aton(s.ip)}
        idx = [i for i, s in enumerate(self.rows) if keep(s)]
        for n in reversed(range(len(self.sort))):  # sort estable: del último criterio al primero
            col, rev = self.sort[n]
            key = keys[col]
            if col == 'ping' and n < len(self.sort) - 1:
                key = lambda s: ping_key(s) // 20  # en ms exactos casi nunca empatan y el 2.º criterio no haría nada
            idx.sort(key=lambda i: key(self.rows[i]), reverse=rev)
        pos = {c: n for n, (c, _) in enumerate(self.sort)}
        for c in COLS:
            mark = ''
            if c in pos:
                mark = (' ▼' if self.sort[pos[c]][1] else ' ▲') + (str(pos[c] + 1) if len(self.sort) > 1 else '')
            self.tree.heading(c, text=self.t('col_' + c) + mark)
        self.tree.delete(*self.tree.get_children())
        self.by_ip, self.shown = {}, len(idx)
        for i in idx:
            s = self.rows[i]
            ms = '' if i in self.refreshing else self.ms.get(s.ip, '')
            self.tree.insert('', 'end', iid=str(i), tags=(tag(ms),), values=self.row_values(s, ms))
            self.by_ip.setdefault(s.ip, []).append(str(i))


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        import tempfile
        assert all(len(v) == 2 for v in TEXT.values())
        assert ping('127.0.0.1') is not None
        assert ping('192.0.2.1', timeout_ms=300) is None  # TEST-NET, nunca responde
        rows, src, ts = load_servers()
        assert rows and all(isinstance(s, Server) and s.players > 0 and len(s.modids) <= s.mods for s in rows)
        assert any(s.official for s in rows) and not all(s.official for s in rows)
        assert make_server(rows[0].info) == rows[0]  # refrescar una fila reconstruye el servidor igual
        # historial: fotos de 10, 20 y 30 jugadores -> media 20; reabrir a los 100 s no cuenta; lo de hace 9 días se borra
        tmp, t0 = os.path.join(tempfile.mkdtemp(), 'h.json'), time.time()
        srv = rows[0]._replace(ip='1.2.3.4', port=2302)
        update_history([srv._replace(players=5)], t0 - 9 * 86400, tmp)
        update_history([srv._replace(players=10)], t0 - 7200, tmp)
        assert avg_players(update_history([srv._replace(players=99)], t0 - 7100, tmp), '1.2.3.4:2302', t0) is None
        update_history([srv._replace(players=20)], t0 - 3600, tmp)
        hist = update_history([srv._replace(players=30)], t0, tmp)
        assert len(hist) == 3 and avg_players(hist, '1.2.3.4:2302', t0) == 20 and avg_players(hist, 'x:1', t0) == 0
        assert [act_level(v) for v in (0, 0.5, 1, 10, 30)] == [0, 0, 1, 2, 3]
        print('ok', len(rows), 'servidores,', src)
        sys.exit()
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # texto nítido en pantallas con zoom
    except OSError:
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()
