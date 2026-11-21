import React, {useEffect, useMemo, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {BarChart3, CalendarDays, ChevronDown, Club, Cloud, Crown, Gamepad2, Pencil, Plus, Search, SlidersHorizontal, Trophy, Trash2, UserPlus, Users, X} from 'lucide-react';
import './styles.css';
import './enhancements.css';
import './player-manager.css';
import './visualizations.css';
import './seasons.css';
import './motion.css';
import './season-photos.css';
import './transitions.css';
import './rooms.css';
import './refinement.css';

const tg = window.Telegram?.WebApp;
const passLogo = '/pass-bot-logo.png';
const api = async (path, {roomId, ...options} = {}) => {
  const response = await fetch(`/api${path}`, {...options, headers: {
    'Content-Type': 'application/json', 'X-Telegram-Init-Data': tg?.initData || '',
    ...(roomId ? {'X-Room-Id': String(roomId)} : {}), ...options.headers,
  }});
  if (!response.ok) {
    const {detail} = await response.json().catch(() => ({}));
    throw new Error(typeof detail === 'string' ? detail : response.status === 422
      ? 'Проверьте заполненные поля.' : 'Не удалось выполнить запрос.');
  }
  return response.status === 204 ? null : response.json();
};
function SecureImage({path, alt, roomId}) {
  const [url, setUrl] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl;
    setUrl('');
    fetch(path, {signal: controller.signal, headers: {
      'X-Telegram-Init-Data': tg?.initData || '', 'X-Room-Id': String(roomId),
    }}).then(response => {
      if (!response.ok) throw new Error();
      return response.blob();
    }).then(blob => {
      if (controller.signal.aborted) return;
      objectUrl = URL.createObjectURL(blob);
      setUrl(objectUrl);
    }).catch(() => {});
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [path, roomId]);
  return url ? <img src={url} alt={alt}/> : <span className="image-placeholder" role="status">Фото сезона</span>;
}
const formatMoney = (value) => new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 0}).format(value) + ' ₽';
const gameDate = value => new Date(`${value}T00:00:00`).toLocaleDateString('ru-RU', {day: 'numeric', month: 'short', year: 'numeric'});
const emptyFilters = () => ({city: '', winner: '', participant: '', date_from: '', date_to: ''});

function AnimatedNumber({value, format = number => Math.round(number)}) {
  const target = Number(value) || 0;
  const [current, setCurrent] = useState(0);
  useEffect(() => {
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) { setCurrent(target); return undefined; }
    let frame;
    const startedAt = performance.now();
    const duration = 700;
    const tick = now => { const progress = Math.min((now - startedAt) / duration, 1); setCurrent(target * (1 - Math.pow(1 - progress, 3))); if (progress < 1) frame = requestAnimationFrame(tick); };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target]);
  return format(current);
}
function LoadingScreen({label}) { return <main className="center loading-screen"><div className="poker-chip" aria-hidden="true"><i>♠</i></div><span>{label}</span></main>; }
function useRequest(path, roomId, delay = 0) {
  const [result, setResult] = useState(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api(path, {roomId, signal: controller.signal}).then(
        data => { if (!controller.signal.aborted) setResult({path, roomId, attempt, data}); },
        error => { if (!controller.signal.aborted) setResult({path, roomId, attempt, error: error.message}); },
      );
    }, delay);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [path, roomId, delay, attempt]);
  const current = path && result?.path === path && result.roomId === roomId && result.attempt === attempt ? result : {};
  return {...current, retry: () => setAttempt(value => value + 1)};
}

function RequestStatus({request, label = 'Загружаем…'}) {
  return request.error
    ? <div className="inline-error" role="alert"><p>{request.error}</p><button onClick={request.retry}>Повторить</button></div>
    : <p className="empty" role="status">{label}</p>;
}

function useTelegramBack(handler, confirmClosing = false) {
  const callback = useRef(handler);
  useEffect(() => { callback.current = handler; }, [handler]);
  const enabled = Boolean(handler);
  useEffect(() => {
    const back = tg?.BackButton;
    const press = () => callback.current?.();
    if (enabled) { back?.show(); back?.onClick(press); }
    if (confirmClosing) tg?.enableClosingConfirmation?.();
    return () => {
      if (enabled) { back?.offClick(press); back?.hide(); }
      if (confirmClosing) tg?.disableClosingConfirmation?.();
    };
  }, [enabled, confirmClosing]);
}

function App() {
  const request = useRequest('/rooms');
  const [addedRooms, setAddedRooms] = useState([]);
  const [selectedId, setSelectedId] = useState(() => Number(localStorage.getItem('poker-active-room')));
  const [picker, setPicker] = useState(false);
  const [newCode, setNewCode] = useState(null);
  useEffect(() => {
    tg?.ready?.();
    tg?.expand?.();
    tg?.setHeaderColor?.('#111114');
    tg?.setBackgroundColor?.('#111114');
    tg?.setBottomBarColor?.('#111114');
  }, []);
  const rooms = [...(request.data || []), ...addedRooms.filter(room => !request.data?.some(item => item.id === room.id))];
  const room = rooms.find(item => item.id === selectedId);
  function select(item) {
    localStorage.setItem('poker-active-room', String(item.id));
    setSelectedId(item.id);
    setPicker(false);
  }
  function add(item, code) {
    setAddedRooms(current => current.some(room => room.id === item.id) ? current : [...current, item]);
    if (code) setNewCode({roomId: item.id, code});
    select(item);
  }
  if (!request.data) return (request.error ? <main className="center"><h1>PASS Stats</h1><RequestStatus request={request}/></main> : <LoadingScreen label="Проверяем доступ…"/>);
  const gate = <RoomGate rooms={rooms} onSelect={select} onCreated={({room, code}) => add(room, code)} onJoined={add} onCancel={room ? () => setPicker(false) : null}/>;
  if (!room) return gate;
  return <><div hidden={picker}><RoomScreen key={room.id} room={room} onSwitch={() => setPicker(true)} initialCode={newCode?.roomId === room.id ? newCode.code : ''} onDismissCode={() => setNewCode(null)}/></div>{picker && gate}</>;
}

function RoomScreen({room, onSwitch, initialCode, onDismissCode}) {
  const [data, setData] = useState(null);
  const [tab, setTab] = useState('home');
  const [form, setForm] = useState(null);
  const [playerForm, setPlayerForm] = useState(false);
  const [detail, setDetail] = useState(null);
  const [notice, setNotice] = useState('');
  const [invitation, setInvitation] = useState(initialCode);
  const [menu, setMenu] = useState(false);
  const [menuError, setMenuError] = useState('');
  const [rotating, setRotating] = useState(false);
  const [historyVersion, setHistoryVersion] = useState(0);
  const [historyOptions, setHistoryOptions] = useState({search: '', filters: emptyFilters()});
  const bootstrap = useRequest('/bootstrap', room.id);
  useEffect(() => { if (bootstrap.data) setData(bootstrap.data); }, [bootstrap.data]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(''), 2600);
    return () => clearTimeout(timer);
  }, [notice]);
  function changed(message) {
    bootstrap.retry();
    setHistoryVersion(value => value + 1);
    setNotice(message);
    tg?.HapticFeedback?.notificationOccurred?.('success');
  }
  async function rotateInvitation() {
    if (rotating || !confirm('Старый код перестанет работать. Создать новый?')) return;
    setRotating(true);
    setMenuError('');
    try {
      const result = await api(`/rooms/${room.id}/code`, {roomId: room.id, method: 'POST'});
      setInvitation(result.code);
      setMenu(false);
    } catch (error) { setMenuError(error.message); }
    finally { setRotating(false); }
  }
  function openNewGame() {
    const date = new Date();
    const localDate = [date.getFullYear(), String(date.getMonth() + 1).padStart(2, '0'), String(date.getDate()).padStart(2, '0')].join('-');
    setForm({date: localDate, city: data.cities[0] || '', players_count: 2, winner: '', second_place: '', participants: [], rebuys: 0, buyin: 350, big_blind: 10, was_hookah: false, beer_liters: 0, description: '', is_archive: false});
  }
  async function submit(payload) {
    await api(form.id ? `/games/${form.id}` : '/games', {roomId: room.id, method: form.id ? 'PUT' : 'POST', body: JSON.stringify(payload)});
    changed(form.id ? 'Изменения сохранены' : 'Игра добавлена');
    setForm(null);
    setDetail(null);
    setTab('games');
  }
  async function removeGame() {
    await api(`/games/${form.id}`, {roomId: room.id, method: 'DELETE'});
    changed('Игра удалена');
    setForm(null);
    setDetail(null);
  }
  if (!data) return bootstrap.error ? <main className="center"><RequestStatus request={bootstrap}/><button onClick={onSwitch}>Выбрать комнату</button></main> : <LoadingScreen label="Загружаем статистику…"/>;
  const tabs = [['home', Gamepad2, 'Главная'], ['games', CalendarDays, 'Игры'], ['season', Trophy, 'Сезон'], ['stats', BarChart3, 'Статистика']];
  return <main>
    <header className="app-header">
      <img className="app-logo" src={passLogo} alt="PASS Stats"/>
      <button className="room-trigger" onClick={() => setMenu(!menu)} aria-expanded={menu}><span>{room.name}</span><ChevronDown size={16}/></button>
    </header>
    {menu && <section className="room-menu">
      <button onClick={onSwitch}>Сменить комнату</button>
      {room.role === 'owner' && <button disabled={rotating} onClick={rotateInvitation}>Новый код приглашения</button>}
      {menuError && <p className="room-error" role="alert">{menuError}</p>}
    </section>}
    {invitation && <section className="invitation"><strong>Код приглашения</strong><b>{invitation}</b>
      <button onClick={async () => {
        try { await navigator.clipboard.writeText(invitation); setNotice('Код скопирован'); }
        catch { setNotice('Выделите код и скопируйте вручную'); }
      }}>Скопировать код</button>
      <button onClick={() => { setInvitation(''); onDismissCode(); }}>Готово</button>
    </section>}
    <div className="tab-panel" key={tab}>
      {tab === 'home' && <Home data={data} onAdd={openNewGame} onAddPlayer={() => setPlayerForm(true)} onGames={() => setTab('games')} onGame={setDetail}/>}
      {tab === 'games' && <GameHistory version={historyVersion} roomId={room.id} options={historyOptions} setOptions={setHistoryOptions} cities={data.cities} players={data.players} onAdd={openNewGame} onEdit={setDetail}/>}
      {tab === 'season' && <RoomSeasons roomId={room.id}/>}
      {tab === 'stats' && <Stats players={data.players} roomId={room.id}/>}
    </div>
    {detail && !form && <GameDetails id={detail} roomId={room.id} onClose={() => setDetail(null)} onEdit={setForm}/>}
    {form && <GameForm game={form} players={data.players} cities={data.cities} onClose={() => setForm(null)} onSubmit={submit} onDelete={removeGame}/>}
    {playerForm && <PlayerForm roomId={room.id} onClose={() => setPlayerForm(false)} onCreated={() => { setPlayerForm(false); changed('Игрок добавлен'); }}/>}
    {notice && <div className="notice" role="status">{notice}</div>}
    <nav aria-label="Разделы">{tabs.map(([key, Icon, label]) => <button className={tab === key ? 'active' : ''} aria-current={tab === key ? 'page' : undefined} onClick={() => { setTab(key); window.scrollTo(0, 0); }} key={key}><Icon size={20}/>{label}</button>)}</nav>
  </main>;
}

function RoomSeasons({roomId}) {
  const [selection, setStart] = useState(null);
  const list = useRequest('/seasons', roomId);
  const start = selection ?? list.data?.find(item => item.is_current)?.start ?? '';
  const detail = useRequest(start ? `/season?start=${start}` : null, roomId);
  if (!list.data) return <RequestStatus request={list}/>;
  return <SeasonListV2Base roomId={roomId} season={detail.data} seasons={list.data} selectedStart={start} onSelect={setStart}
    detailRequest={detail} onSaved={() => { list.retry(); detail.retry(); }}/>;
}

function GameDetails({id, roomId, onClose, onEdit}) {
  const request = useRequest(`/games/${id}`, roomId);
  useTelegramBack(onClose);
  const game = request.data;
  return <div className="modal" role="dialog" aria-modal="true" aria-label="Детали игры"><section className="dialog-content">
    <div className="form-head"><h2>{game?.city || 'Детали игры'}</h2><button aria-label="Закрыть" onClick={onClose}>×</button></div>
    {game ? <>
      <p className="game-meta">{gameDate(game.date)}{game.is_archive ? ' · Архив' : ''}</p>
      <p className="bank">Банк <b>{formatMoney(game.bank)}</b></p>
      <dl className="game-facts">
        <dt>Победитель</dt><dd>{game.winner}</dd><dt>Второе место</dt><dd>{game.second_place}</dd>
        <dt>Игроков</dt><dd>{game.players_count}</dd><dt>Бай-ин</dt><dd>{formatMoney(game.buyin)}</dd>
        <dt>Ребаев</dt><dd>{game.rebuys}</dd><dt>Количество бобиков</dt><dd>{game.big_blind}</dd>
        <dt>Кальян</dt><dd>{game.was_hookah ? 'Да' : 'Нет'}</dd><dt>Пива, л</dt><dd>{game.beer_liters ?? 0}</dd>
      </dl>
      {!!game.participants?.length && <p className="game-meta">{game.participants.map(name => game.player_rebuys?.[name] ? `${name} (+${game.player_rebuys[name]})` : name).join(' · ')}</p>}
      {game.description && <p className="game-description">{game.description}</p>}
      <button className="primary submit" onClick={() => onEdit(game)}><Pencil size={17}/>Редактировать</button>
    </> : <RequestStatus request={request}/>}
  </section></div>;
}

function RoomGate({rooms, onSelect, onCreated, onJoined, onCancel}) {
  useTelegramBack(onCancel);
  const [mode, setMode] = useState(rooms.length ? 'choose' : 'create');
  const [name, setName] = useState(''), [code, setCode] = useState(''), [error, setError] = useState(''), [saving, setSaving] = useState(false);
  const submit = async event => { event.preventDefault(); setError(''); setSaving(true); try { if (mode === 'create') onCreated(await api('/rooms', {method: 'POST', body: JSON.stringify({name})})); else onJoined((await api('/rooms/join', {method: 'POST', body: JSON.stringify({code})})).room); } catch (e) {setError(e.message);} finally {setSaving(false);} };
  return <main className="room-gate"><section className="hero room-gate__hero"><img className="room-gate__logo" src={passLogo} alt="PASS Stats"/><div><p>PRIVATE TABLE</p><h2>{rooms.length && mode === 'choose' ? 'Выберите комнату' : mode === 'create' ? 'Создайте свою комнату' : 'Войдите в комнату'}</h2><span>Приватная статистика вашей игры.</span></div></section>{mode === 'choose' && <section className="room-list">{rooms.map(item => <button key={item.id} onClick={() => onSelect(item)}><strong>{item.name}</strong><small>{item.role === 'owner' ? 'Владелец' : 'Участник'}</small></button>)}</section>}{mode !== 'choose' && <form className="room-form" onSubmit={submit}>{mode === 'create' ? <label>Название комнаты<input required maxLength="120" value={name} onChange={event => setName(event.target.value)} placeholder="Например, Покер по пятницам"/></label> : <label>Код приглашения<input required value={code} onChange={event => setCode(event.target.value.toUpperCase())} placeholder="POKER-…" autoCapitalize="characters"/></label>}{error && <p className="room-error">{error}</p>}<button className="primary" disabled={saving} type="submit">{saving ? 'Подождите…' : mode === 'create' ? 'Создать комнату' : 'Войти'}</button></form>}<section className="room-actions">{mode !== 'create' && <button onClick={() => setMode('create')}>Создать комнату</button>}{mode !== 'join' && <button onClick={() => setMode('join')}>Стать частью существующей</button>}{mode !== 'choose' && rooms.length > 0 && <button onClick={() => setMode('choose')}>Мои комнаты</button>}{onCancel && <button onClick={onCancel}>Отмена</button>}</section></main>
}
function Home({data, onAdd, onAddPlayer, onGames, onGame}) { return <><section className="home-actions"><button onClick={onAdd}><Club size={30}/><span>Новая игра</span></button><button onClick={onAddPlayer}><UserPlus size={30}/><span>Новый игрок</span></button></section><section className="metrics home-metrics"><Metric icon={<Gamepad2/>} label="Игр" value={data.summary.games}/><Metric icon={<Trophy/>} label="Общий банк" value={data.summary.bank} format={formatMoney} chips/></section><section className="section-title"><h3>Последние игры</h3><button onClick={onGames}>Все</button></section><GameCards games={data.recent_games} onEdit={onGame}/></> }
function Metric({icon, label, value, animated = false, format = item => Number.isInteger(value) ? Math.round(item) : item, chips = false}) { return <article className={`metric ${chips ? 'metric--bank' : ''}`}>{icon}<span>{label}</span><strong>{animated ? <AnimatedNumber value={value} format={format}/> : format(value)}</strong>{chips && <i className="chip-stack" aria-hidden="true"><b/><b/><b/></i>}</article> }
function Games({search, setSearch, filters, setFilters, cities, players, onAdd, children}) {
  const [filtersOpen, setFiltersOpen] = useState(false);
  const update = (key, value) => setFilters({...filters, [key]: value});
  const clear = () => setFilters({city: '', winner: '', participant: '', date_from: '', date_to: ''});
  const activeFilters = Object.values(filters).filter(Boolean).length;
  return <><section className="section-title"><h2>История игр</h2><button className="round" onClick={onAdd} aria-label="Добавить игру"><Plus/></button></section><label className="search"><Search size={18}/><input aria-label="Поиск игр" value={search} onChange={e => setSearch(e.target.value)} placeholder="Город, дата или победитель"/></label><button className={`filter-toggle ${filtersOpen || activeFilters ? 'selected' : ''}`} onClick={() => setFiltersOpen(!filtersOpen)}><SlidersHorizontal size={17}/>Фильтры{activeFilters ? ` · ${activeFilters}` : ''}<ChevronDown size={16}/></button>{filtersOpen && <section className="filters"><label>Город<select aria-label="Город" value={filters.city} onChange={e => update('city', e.target.value)}><option value="">Все города</option>{cities.map(city => <option key={city} value={city}>{city}</option>)}</select></label><label>Победитель<select aria-label="Победитель" value={filters.winner} onChange={e => update('winner', e.target.value)}><option value="">Все победители</option>{players.map(player => <option key={player} value={player}>{player}</option>)}</select></label><label>Участник<select aria-label="Участник" value={filters.participant} onChange={e => update('participant', e.target.value)}><option value="">Любой участник</option>{players.map(player => <option key={player} value={player}>{player}</option>)}</select></label><label>С даты<input type="date" value={filters.date_from} onChange={e => update('date_from', e.target.value)}/></label><label>По дату<input type="date" value={filters.date_to} onChange={e => update('date_to', e.target.value)}/></label><button className="clear-filters" onClick={clear}><X size={15}/>Сбросить</button></section>}{children}</> }
function isFreshGame(game) {
  if (!game.created_at) return false;
  const timestamp = /Z$|[+-]\d{2}:\d{2}$/.test(game.created_at) ? game.created_at : game.created_at + 'Z';
  const age = Date.now() - new Date(timestamp).getTime();
  return age >= 0 && age < 3 * 86_400_000;
}
function GameCards({games, onEdit}) {
  return <section className="cards">{games.length ? games.map(game =>
    <button className="game" key={game.id} onClick={() => onEdit(game.id)}>
      <span className="game-details"><strong><Crown size={15}/>{game.winner}</strong>
        <span className="game-meta">{game.city} · {gameDate(game.date)}{game.was_hookah && ' · 💨'}</span>
        {game.is_archive ? <span className="archive-badge">Архив</span> : isFreshGame(game) && <span className="new-game-badge">Новая</span>}
      </span>
      <span className="game-result"><b>{formatMoney(game.bank)}</b><span className="players"><Users size={14}/>{game.players_count}</span></span>
    </button>) : <p className="empty">Игр не найдено</p>}</section>;
}

function GameHistory({roomId, options, setOptions, version, ...props}) {
  const query = new URLSearchParams();
  Object.entries({...options.filters, search: options.search.trim()}).forEach(([key, value]) => { if (value) query.set(key, value); });
  return <Games {...props} {...options} setSearch={search => setOptions({...options, search})}
    setFilters={filters => setOptions({...options, filters})}>
    <PagedGames key={`${version}:${query}`} query={query.toString()} roomId={roomId} onEdit={props.onEdit}/>
  </Games>;
}
const PAGE_SIZE = 30;
function PagedGames({roomId, query, onEdit}) {
  const [offset, setOffset] = useState(0);
  const [previous, setPrevious] = useState([]);
  const request = useRequest(`/games?limit=${PAGE_SIZE + 1}&offset=${offset}&${query}`, roomId, offset ? 0 : 220);
  const next = request.data?.slice(0, PAGE_SIZE) || [];
  const visible = [...previous, ...next.filter(game => !previous.some(item => item.id === game.id))];
  return <>
    {(request.data || previous.length > 0) && <GameCards games={visible} onEdit={onEdit}/>}
    {!request.data && <RequestStatus request={request}/>}
    {request.data?.length > PAGE_SIZE && <button className="load-more" onClick={() => {
      setPrevious(visible);
      setOffset(offset + PAGE_SIZE);
    }}>Показать ещё</button>}
  </>;
}

function PlayerForm({roomId, onClose, onCreated}) {
  const [error, setError] = useState('');

  const [name, setName] = useState(''), [saving, setSaving] = useState(false);
  function close() { if (!saving && (!name.trim() || confirm('Закрыть без сохранения изменений?'))) onClose(); }
  useTelegramBack(close, Boolean(name.trim()));
  const submit = async event => { event.preventDefault(); if (!name.trim() || saving) return; setError(''); setSaving(true); try { await api('/players', {roomId, method: 'POST', body: JSON.stringify({name: name.trim()})}); await onCreated(); } catch (error) { setError(error.message); } finally { setSaving(false); } };
  return <div className="modal" role="dialog" aria-modal="true" aria-label="Новый игрок"><form className="player-form" onSubmit={submit}><section className="form-head"><div><p>НОВЫЙ ИГРОК</p><h2>Добавить игрока</h2></div><button type="button" aria-label="Закрыть" disabled={saving} onClick={close}>×</button></section><label>Имя игрока<input autoFocus value={name} onChange={event => setName(event.target.value)} placeholder="Введите имя" maxLength="120" required/></label>{error && <p className="inline-error" role="alert">{error}</p>}<button className="primary submit" type="submit" disabled={saving}>{saving ? 'Добавляем…' : 'Добавить игрока'}</button></form></div>
}
function Stats({players, roomId}) {
  const [period, setPeriod] = useState({date_from: '', date_to: ''});
  const [view, setView] = useState('overview');
  const [selected, setSelected] = useState('');
  const query = useMemo(() => {
    const params = new URLSearchParams();
    Object.entries(period).forEach(([key, value]) => value && params.set(key, value));
    return params.toString();
  }, [period]);
  const invalidPeriod = period.date_from && period.date_to && period.date_from > period.date_to;
  const overviewRequest = useRequest(view === 'overview' && !invalidPeriod ? `/stats?${query}` : null, roomId);
  const playerRequest = useRequest(view === 'players' && selected && !invalidPeriod ? `/players/${encodeURIComponent(selected)}?${query}` : null, roomId);
  const overview = overviewRequest.data;
  const stats = playerRequest.data;

  const month = value => new Date(`${value}-01T00:00:00`).toLocaleDateString('ru-RU', {month: 'short', year: 'numeric'});
  const setDate = (key, value) => setPeriod({...period, [key]: value});
  const months = overview?.months || [];
  const maxMonthlyBank = Math.max(...months.map(item => item.bank), 1);
  const calendarMonth = value => Number(value.slice(0, 4)) * 12 + Number(value.slice(5));
  const firstMonth = months.length ? calendarMonth(months[0].month) : 0;
  const distance = months.length ? calendarMonth(months.at(-1).month) - firstMonth : 0;
  const points = months.map(item => ({
    x: distance ? 3 + (calendarMonth(item.month) - firstMonth) / distance * 94 : 50,
    y: 48 - item.bank / maxMonthlyBank * 42,
  }));
  const trendPoints = points.map(({x, y}) => `${x},${y}`).join(' ');
  const peakMonth = months.reduce((peak, item) => !peak || item.bank > peak.bank ? item : peak, null);

  return <>
    <section className="section-title"><h2>Статистика</h2></section>
    <div className="segments" aria-label="Тип статистики">{[['overview', 'Общая'], ['players', 'По игрокам']].map(([key, label]) => <button key={key} aria-pressed={view === key} onClick={() => setView(key)}>{label}</button>)}</div>
    <details className="period-picker"><summary>{[period.date_from, period.date_to].filter(Boolean).map(gameDate).join(' — ') || 'Период · За всё время'}</summary><button className="clear-link" onClick={() => setPeriod({date_from: '', date_to: ''})}>За всё время</button>
    <section className="period"><label>С даты<input type="date" value={period.date_from} onChange={e => setDate('date_from', e.target.value)}/></label><label>По дату<input type="date" value={period.date_to} onChange={e => setDate('date_to', e.target.value)}/></label></section></details>
    {invalidPeriod && <p role="alert" className="inline-error">Начало периода должно быть раньше окончания.</p>}
    {!invalidPeriod && view === 'overview' && !overview && <RequestStatus request={overviewRequest}/>}
    {overview && <>
      <section className="metrics stats-metrics"><Metric icon={<Gamepad2/>} label="Игр" value={overview.summary.games}/><Metric icon={<Trophy/>} label="Общий банк" value={formatMoney(overview.summary.bank)}/><Metric icon={<Users/>} label="Среднее игроков" value={overview.summary.avg_players}/><Metric icon={<Plus/>} label="Среднее ребаев" value={overview.summary.avg_rebuys}/></section><div className="stats-extras"><span className="quiet-stat"><Cloud size={14}/>Дымных сессий: {overview.summary.hookah_sessions}</span><span className="quiet-stat">Пива выпито: {overview.summary.beer_liters} л</span></div>
      {overview.records.biggest_game ? <article className="record"><span>Рекордный банк</span><strong>{formatMoney(overview.records.biggest_game.bank)}</strong><small>{new Date(`${overview.records.biggest_game.date}T00:00:00`).toLocaleDateString('ru-RU')} · {overview.records.biggest_game.city} · победил {overview.records.biggest_game.winner}</small></article> : <p className="empty">За этот период пока нет игр</p>}
      <section className="section-title"><h3>Города</h3></section>
      <section className="city-list">{overview.cities.map(city => <article key={city.name}><div><strong>{city.name}</strong><small>{city.games} игр · средний банк {formatMoney(city.avg_bank)}</small></div><span><b>{city.leader.name}</b><small>{city.leader.wins} побед</small></span></article>)}</section>
      <section className="section-title"><h3>Динамика по месяцам</h3></section>
      {months.length ? <section className="monthly-trend" aria-label="Банк по месяцам"><div><span>Пик: <b>{formatMoney(peakMonth.bank)}</b> · {month(peakMonth.month)}</span><svg viewBox="0 0 100 52" preserveAspectRatio="none" role="img" aria-label="Изменение банка по месяцам"><polyline points={trendPoints}/>{points.map(({x, y}, index) => <circle key={months[index].month} cx={x} cy={y} r="1.4"/>) }</svg><small>{month(months[0].month)} — {month(months[months.length - 1].month)}</small></div><details><summary>Показать помесячные цифры</summary><section>{months.map(item => <article key={item.month}><span>{month(item.month)}</span><b>{formatMoney(item.bank)}</b><small>{item.games} игр · {item.avg_players} игроков</small></article>)}</section></details></section> : <p className="empty">За этот период пока нет игр</p>}
    </>}
    {view === 'players' && <>
    <section className="section-title"><h3>Игроки</h3></section>
    {!players.length && <p className="empty">В комнате пока нет игроков</p>}
    {selected && !stats && !invalidPeriod && <RequestStatus request={playerRequest}/>}
    <section className="chips">{players.map(name => <button onClick={() => setSelected(name)} className={selected === name ? 'selected' : ''} key={name}>{name}</button>)}</section>
    {stats && <section className="profile"><h2>{stats.name}</h2><div className="metrics"><Metric icon={<Gamepad2/>} label="Игр" value={stats.games}/><Metric icon={<Crown/>} label="Побед" value={stats.wins}/><Metric icon={<Trophy/>} label="Топ‑2" value={`${stats.top2_rate}%`}/><Metric icon={<BarChart3/>} label="Винрейт" value={`${stats.win_rate}%`}/></div><section className="player-facts"><span>Выиграно банков <b>{formatMoney(stats.bank_won)}</b></span><span>Лучшая серия <b>{stats.best_win_streak} побед</b></span><span>Текущая серия <b>{stats.current_win_streak} побед</b></span></section><SeasonComparison data={stats.season_comparison}/></section>}
    </>}
  </>;
}

function SeasonComparison({data}) { const current = data.current, previous = data.previous; const winDelta = current.win_rate - previous.win_rate; const gamesDelta = current.games - previous.games; const sign = number => number > 0 ? '+' : ''; return <section className="comparison"><h3>Сравнение с прошлым сезоном</h3><p>Текущий: {new Date(`${data.start}T00:00:00`).toLocaleDateString('ru-RU')} — {new Date(`${data.end}T00:00:00`).toLocaleDateString('ru-RU')}</p><div><span>Игр <b>{current.games}</b><small>{sign(gamesDelta)}{gamesDelta} к прошлому</small></span><span>Винрейт <b>{current.win_rate}%</b><small>{sign(winDelta)}{winDelta.toFixed(1)} п.п.</small></span><span>Топ‑2 <b>{current.top2_rate}%</b><small>было {previous.top2_rate}%</small></span></div></section> }
function GameForm({game, players, cities, onClose, onSubmit, onDelete}) {
  const [value, setValue] = useState(game);
  const [newPlayer, setNewPlayer] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const dirty = value !== game || Boolean(newPlayer.trim());
  const participants = value.participants || [];
  const pool = [...new Set([...players, ...participants])];
  const rebuys = value.player_rebuys || {};
  const totalRebuys = Number(value.rebuys);
  const allocated = Object.values(rebuys).reduce((sum, count) => sum + count, 0);
  const legacyRebuys = game.id && !game.is_archive && !value.is_archive
    && game.rebuys === totalRebuys && totalRebuys > 0 && !Object.keys(game.player_rebuys || {}).length && !allocated;
  const playerCount = value.is_archive ? Number(value.players_count) : participants.length;
  const bank = (playerCount + totalRebuys) * Number(value.buyin || 0);
  function set(key, next) { setValue(current => ({...current, [key]: next})); }
  function close() {
    if (!saving && (!dirty || confirm('Закрыть без сохранения изменений?'))) onClose();
  }
  useTelegramBack(close, dirty);
  function updateParticipants(next) {
    setValue(current => ({...current, participants: next,
      winner: next.includes(current.winner) ? current.winner : '',
      second_place: next.includes(current.second_place) ? current.second_place : '',
      player_rebuys: Object.fromEntries(Object.entries(rebuys).filter(([name]) => next.includes(name))),
    }));
  }
  function addPlayer() {
    const name = newPlayer.trim();
    if (!name) return;
    const existing = pool.find(player => player.toLocaleLowerCase('ru-RU') === name.toLocaleLowerCase('ru-RU'));
    if (!participants.includes(existing || name) && participants.length < 30) updateParticipants([...participants, existing || name]);
    setNewPlayer('');
  }
  async function run(action) {
    if (saving) return;
    setSaving(true);
    setError('');
    try { await action(); }
    catch (error) { setError(error.message); }
    finally { setSaving(false); }
  }
  function save(event) {
    event.preventDefault();
    if (playerCount < 2) return setError('Выберите минимум двух участников.');
    if (value.winner.trim() === value.second_place.trim()) return setError('Победитель и второе место должны быть разными.');
    if (!value.is_archive && !legacyRebuys && allocated !== totalRebuys) return setError('Распределите все ребаи между участниками.');
    run(() => onSubmit({...value, city: value.city.trim(), winner: value.winner.trim(), second_place: value.second_place.trim(),
      players_count: playerCount, participants: value.is_archive ? [] : participants,
      player_rebuys: value.is_archive ? {} : rebuys, rebuys: totalRebuys,
      buyin: Number(value.buyin), big_blind: Number(value.big_blind), beer_liters: Number(value.beer_liters || 0),
    }));
  }
  const numberField = (label, key, min, max, step = 1) => <label>{label}<input type="number" min={min} max={max} step={step} value={value[key] ?? 0} onChange={event => set(key, event.target.value)} required/></label>;
  const place = (label, key, other) => <label>{label}{value.is_archive
    ? <input value={value[key]} maxLength={120} onChange={event => set(key, event.target.value)} required/>
    : <select aria-label={label} value={value[key]} onChange={event => set(key, event.target.value)} required><option value="">Выберите</option>
      {participants.map(name => <option key={name} disabled={name === value[other]}>{name}</option>)}</select>}</label>;
  return <div className="modal" role="dialog" aria-modal="true" aria-label={game.id ? 'Редактировать игру' : 'Новая игра'}>
    <form className="game-form" onSubmit={save}>
      <div className="form-head"><h2>{game.id ? 'Редактировать игру' : 'Новая игра'}</h2><button type="button" aria-label="Закрыть" onClick={close}>×</button></div>
      <fieldset disabled={saving}>
        <div className="fields">
          <label>Дата<input type="date" value={value.date} onChange={event => set('date', event.target.value)} required/></label>
          <label>Город<input list="cities" value={value.city} maxLength={120} onChange={event => set('city', event.target.value)} required/>
            <datalist id="cities">{cities.map(city => <option key={city} value={city}/>)}</datalist></label>
        </div>
        <label className="archive-choice"><input type="checkbox" checked={value.is_archive} onChange={event => set('is_archive', event.target.checked)}/> Архивная игра: состав неизвестен</label>
        {value.is_archive ? <>
          <p className="game-meta">Архив будет виден в истории и сводке сезона. Личная и общая статистика его не учитывают.</p>
          <div className="fields">{numberField('Игроков', 'players_count', 2, 30)}</div>
        </> : <section className="form-section">
          <h3>Участники <span>{participants.length}</span></h3>
          {!!pool.length && <div className="chips">{pool.map(name => <button type="button" key={name} aria-pressed={participants.includes(name)}
            className={participants.includes(name) ? 'selected' : ''} disabled={participants.length >= 30 && !participants.includes(name)}
            onClick={() => updateParticipants(participants.includes(name) ? participants.filter(player => player !== name) : [...participants, name])}>{name}</button>)}</div>}
          <div className="inline-player"><label>Новый участник<input value={newPlayer} maxLength={120} onChange={event => setNewPlayer(event.target.value)}
            onKeyDown={event => { if (event.key === 'Enter' && !event.nativeEvent.isComposing) { event.preventDefault(); addPlayer(); } }} placeholder="Имя игрока"/></label>
            <button type="button" aria-label="Добавить участника" disabled={!newPlayer.trim() || participants.length >= 30} onClick={addPlayer}><Plus size={19}/></button>
          </div>
        </section>}
        <div className="fields">{place('Победитель', 'winner', 'second_place')}{place('Второе место', 'second_place', 'winner')}</div>
        <section className="form-section">
          <h3>Банк и ребаи</h3>
          <div className="fields">{numberField('Бай-ин, ₽', 'buyin', 0.01, undefined, 'any')}{numberField('Ребаев', 'rebuys', 0, 100)}</div>
          {!value.is_archive && (totalRebuys > 0 || allocated > 0) && <details className="form-extra">
            <summary>Распределить ребаи · {allocated} из {totalRebuys}</summary>
            {legacyRebuys && <p className="game-meta">В старой записи есть только общее количество. Распределение можно оставить пустым.</p>}
            <div className="rebuy-allocation__list">{participants.map(name => <div key={name}><span>{name}</span><section>
              <button type="button" aria-label={`Уменьшить ребаи: ${name}`} disabled={!rebuys[name]} onClick={() => set('player_rebuys', {...rebuys, [name]: (rebuys[name] || 0) - 1})}>−</button>
              <b>{rebuys[name] || 0}</b>
              <button type="button" aria-label={`Увеличить ребаи: ${name}`} disabled={allocated >= totalRebuys} onClick={() => set('player_rebuys', {...rebuys, [name]: (rebuys[name] || 0) + 1})}>+</button>
            </section></div>)}</div>
          </details>}
        </section>
        <details className="form-extra">
          <summary>Дополнительно</summary>
          <div className="fields">{numberField('Количество бобиков', 'big_blind', 0.01, undefined, 'any')}{numberField('Пива, л', 'beer_liters', 0, 100, 0.5)}</div>
          <label className="archive-choice"><input type="checkbox" checked={value.was_hookah} onChange={event => set('was_hookah', event.target.checked)}/> Был кальян</label>
          <label>Описание<textarea value={value.description || ''} maxLength={2000} onChange={event => set('description', event.target.value)} placeholder="Необязательно"/></label>
        </details>
        {game.id && <button type="button" className="danger" onClick={() => { if (confirm('Удалить игру без возможности восстановления?')) run(onDelete); }}><Trash2 size={16}/>Удалить игру</button>}
        <div className="form-actions">
          {error && <p className="inline-error" role="alert">{error}</p>}
          <p>Рассчитанный банк <b>{formatMoney(bank)}</b></p>
          <button className="primary submit" type="submit">{saving ? 'Подождите…' : game.id ? 'Сохранить изменения' : 'Сохранить игру'}</button>
        </div>
      </fieldset>
    </form>
  </div>;
}

function roman(number) { const values = [[10,'X'],[9,'IX'],[5,'V'],[4,'IV'],[1,'I']]; let result = ''; for (const [value, symbol] of values) { while (number >= value) { result += symbol; number -= value; } } return result; }
function ArchiveResults({season}) { if (!season?.archive_games) return null; return <section className="archive-results"><h3>Архивные результаты</h3><p>{season.archive_games} игр без подтверждённого состава. Это не рейтинг и не влияет на статистику игроков.</p><section>{season.archive_results.map(item => <article key={item.name}><strong>{item.name}<small>Топ‑2: {item.top2} · выиграно банков: {formatMoney(item.bank_won)}</small></strong><span>🥇 {item.wins} · 🥈 {item.seconds}</span></article>)}</section></section>; }
function SeasonListV2Base({roomId, season, seasons, selectedStart, onSelect, detailRequest, onSaved}) {
  const [editing, setEditing] = useState(false), [title, setTitle] = useState(''), [image, setImage] = useState(null), [preview, setPreview] = useState(null);
  const [saving, setSaving] = useState(false), [error, setError] = useState('');
  useTelegramBack(preview ? () => setPreview(null) : null);
  const current = seasons.find(item => item.is_current) || seasons[0];
  const selected = selectedStart ? season : null;
  const now = new Date();
  const currentStart = current && new Date(`${current.start}T00:00:00`);
  const currentEnd = current && new Date(`${current.end}T23:59:59`);
  const isCurrentSeason = current && now >= new Date(`${current.start}T00:00:00`) && now <= currentEnd;
  const daysLeft = isCurrentSeason ? Math.max(0, Math.ceil((currentEnd.getTime() - now.getTime()) / 86400000)) : null;
  const seasonProgress = isCurrentSeason ? Math.min(1, Math.max(0, (now.getTime() - currentStart.getTime()) / (currentEnd.getTime() - currentStart.getTime()))) : 0;
  useEffect(() => { setTitle(selected?.title || ''); setImage(null); setEditing(false); }, [selected?.start, selected?.title]);
  const chooseImage = event => {
    const file = event.target.files?.[0];
    if (!file) return setImage(null);
    setImage(null);
    if (file.size > 2_000_000) { event.target.value = ''; return setError('Выберите изображение до 2 МБ.'); }
    setError('');
    const reader = new FileReader();
    reader.onload = () => setImage(reader.result);
    reader.onerror = () => setError('Не удалось прочитать фото.');
    reader.readAsDataURL(file);
  };
  const save = async event => {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setError('');
    try {
      await api(`/seasons/${selected.start}/metadata`, {roomId, method: 'PUT', body: JSON.stringify({title, image})});
      setEditing(false);
      onSaved();
    } catch (error) { setError(error.message); }
    finally { setSaving(false); }
  };
  return <>
    {isCurrentSeason && <section className="season-countdown" style={{'--season-progress': seasonProgress}}><p>ТЕКУЩИЙ СЕЗОН</p><strong>{daysLeft} {daysLeft % 10 === 1 && daysLeft % 100 !== 11 ? 'день' : daysLeft % 10 >= 2 && daysLeft % 10 <= 4 && (daysLeft % 100 < 10 || daysLeft % 100 >= 20) ? 'дня' : 'дней'} до конца</strong><div className="season-progress" role="progressbar" aria-label="Прогресс сезона" aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(seasonProgress * 100)}><span/></div><small>{current.label} · прошло {Math.round(seasonProgress * 100)}%</small></section>}
    <section className="section-title"><h2>Сезоны</h2></section>
    <section className="season-list">{seasons.map((item, index) => {
      const isExpanded = selectedStart === item.start;
      return <article key={item.start} className={isExpanded ? 'expanded' : ''}>
        <button className="season-summary" aria-expanded={isExpanded} onClick={() => onSelect(selectedStart === item.start ? '' : item.start)}><span>{roman(seasons.length - index)} · {item.title || 'Сезон'}</span><small>{item.label} · {item.summary.games} игр · {formatMoney(item.summary.bank)}</small>{!item.is_current && <em className="season-podium">{item.winner ? <span>🏆 <b>{item.winner.name}</b><small>победитель · {item.winner.games} игр</small></span> : <span>🏆 Победитель не определён</span>}{item.second_place ? <span>🥈 <b>{item.second_place.name}</b><small>преследователь · {item.second_place.games} игр</small></span> : <span>🥈 Преследователь не определён</span>}</em>}<b>{isExpanded ? 'Свернуть' : 'Подробнее'}</b></button>
        {isExpanded && !selected && <RequestStatus request={detailRequest}/>}
        {isExpanded && selected && <section className="season-expanded">
          {selected.image_url && <button className="season-cover season-detail-cover" onClick={() => setPreview(selected.image_url)}><SecureImage roomId={roomId} path={selected.image_url} alt="Фото сезона"/></button>}
          <button className="season-edit-toggle" onClick={() => { setEditing(!editing); setError(''); }} aria-label="Настроить название и фото сезона" aria-expanded={editing}><Pencil size={16}/> Настроить сезон</button>
          {editing && <form className="season-editor" onSubmit={save}><input value={title} onChange={event => setTitle(event.target.value)} aria-label="Название сезона" placeholder="Название сезона" maxLength="120"/><label>Фото<input type="file" accept="image/png,image/jpeg,image/webp" onChange={chooseImage}/></label>{error && <p className="inline-error" role="alert">{error}</p>}<button className="primary" type="submit" disabled={saving}>Сохранить</button></form>}
          <div className="metrics season-metrics"><Metric icon={<Gamepad2/>} label="Игр" value={selected.summary.games} animated/><Metric icon={<Trophy/>} label="Общий банк" value={selected.summary.bank} format={formatMoney} animated chips/><Metric icon={<Users/>} label="В среднем игроков" value={selected.summary.avg_players}/><Metric icon={<Plus/>} label="В среднем ребаев" value={selected.summary.avg_rebuys}/></div>
          {!selected.is_current && <p className="season-qualification">🏆 Победитель и 🥈 преследователь определяются среди игроков с минимум 5 играми.</p>}<h3>Рейтинг сезона</h3><section className="leaderboard">{selected.leaderboard.map((player, rank) => <article key={player.name} className={`${rank === 0 ? 'leaderboard-leader' : ''} ${!player.eligible ? 'leaderboard-ineligible' : ''}`} style={{'--rank': rank}}><b>{player.eligible ? rank + 1 : '—'}</b><span>{player.name} {!player.eligible && <small className="ineligible-badge">Вне зачёта · нужно 5 игр</small>}<small>{player.games} игр · {player.wins} побед · 🥈 {player.seconds}</small></span><strong><AnimatedNumber value={player.points} format={value => value.toFixed(1)}/></strong></article>)}</section>
          <ArchiveResults season={selected}/>
        </section>}
      </article>;
    })}</section>
    {preview && <div className="photo-preview" role="dialog" aria-label="Фото сезона"><button className="photo-close" onClick={() => setPreview(null)} aria-label="Закрыть фото">×</button><SecureImage roomId={roomId} path={preview} alt="Фото сезона"/></div>}
  </>;
}

createRoot(document.getElementById('root')).render(<App/>);
