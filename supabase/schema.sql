-- =========================================================
--  BritonLauncher — схема базы Supabase
--  Выполнить целиком в SQL Editor проекта.
--  Повторный запуск безопасен: объекты пересоздаются.
-- =========================================================

create extension if not exists pgcrypto with schema extensions;

-- ---------- таблицы ----------

create table if not exists public.profiles (
  nick          text primary key,
  nick_lower    text generated always as (lower(nick)) stored,
  password_hash text not null,
  role          text not null default 'player',
  main_admin    boolean not null default false,
  banned        boolean not null default false,
  ban_reason    text,
  banned_at     timestamptz,
  banned_by     text,
  muted         boolean not null default false,
  mute_reason   text,
  muted_at      timestamptz,
  muted_by      text,
  created_at    timestamptz not null default now(),
  last_login    timestamptz,
  constraint profiles_nick_lower_key unique (nick_lower),
  constraint profiles_role_check check (role in ('admin', 'player'))
);

create index if not exists profiles_role_idx on public.profiles (role);

create table if not exists public.sessions (
  token_hash text primary key,
  nick       text not null references public.profiles (nick) on delete cascade,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null
);

create index if not exists sessions_nick_idx on public.sessions (nick);
create index if not exists sessions_expires_idx on public.sessions (expires_at);

create table if not exists public.launcher_codes (
  code_hash  text primary key,
  nick       text not null references public.profiles (nick) on delete cascade,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  used_at    timestamptz
);

create index if not exists launcher_codes_nick_idx on public.launcher_codes (nick);

create table if not exists public.action_log (
  id      bigserial primary key,
  at      timestamptz not null default now(),
  by_nick text not null,
  action  text not null,
  target  text,
  extra   text
);

create index if not exists action_log_at_idx on public.action_log (at desc);

create table if not exists public.setup_codes (
  nick      text primary key,
  code_hash text not null,
  created_at timestamptz not null default now()
);

insert into public.setup_codes (nick, code_hash)
values
  ('kostyakosmos', '4446e28f6a4eaea236c066c02798d68c6a21f4cd31deda58373beae509302b37'),
  ('britonlauncher', '0d05c578559776e11310d43334f6316e5a6e81e1aae64d65dd1e5986a08e3aec')
on conflict (nick) do nothing;

-- ---------- внутренние помощники ----------

create or replace function public._bl_token_hash(p_token text)
returns text
language sql
immutable
as $$
  select encode(extensions.digest(coalesce(p_token, ''), 'sha256'), 'hex');
$$;

create or replace function public._bl_fixed_admin(p_nick text)
returns boolean
language sql
immutable
as $$
  select lower(coalesce(p_nick, '')) in ('kostyakosmos', 'britonlauncher');
$$;

create or replace function public._bl_profile(p_nick text)
returns jsonb
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select jsonb_build_object(
    'nick', p.nick,
    'role', p.role,
    'main', p.main_admin,
    'banned', p.banned,
    'banReason', coalesce(p.ban_reason, ''),
    'muted', p.muted,
    'muteReason', coalesce(p.mute_reason, ''),
    'created', to_char(p.created_at at time zone 'Europe/Moscow', 'DD.MM.YYYY HH24:MI'),
    'lastLogin', case
      when p.last_login is null then '—'
      else to_char(p.last_login at time zone 'Europe/Moscow', 'DD.MM.YYYY HH24:MI')
    end
  )
  from public.profiles p
  where p.nick = p_nick;
$$;

create or replace function public._bl_session_nick(p_token text)
returns text
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select s.nick
  from public.sessions s
  join public.profiles p on p.nick = s.nick
  where s.token_hash = public._bl_token_hash(p_token)
    and s.expires_at > now();
$$;

create or replace function public._bl_new_session(p_nick text)
returns text
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_token text := encode(extensions.gen_random_bytes(32), 'hex');
begin
  delete from public.sessions where expires_at < now();
  insert into public.sessions (token_hash, nick, expires_at)
  values (public._bl_token_hash(v_token), p_nick, now() + interval '30 days');
  return v_token;
end;
$$;

-- ---------- аккаунты ----------

create or replace function public.bl_claim_fixed_admin(p_nick text, p_password text, p_code text)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_nick text := btrim(coalesce(p_nick, ''));
  v_token text;
  v_setup text;
begin
  if not public._bl_fixed_admin(v_nick) then
    return jsonb_build_object('ok', false, 'error', 'Этот ник не зарезервирован');
  end if;
  if length(coalesce(p_password, '')) < 4 then
    return jsonb_build_object('ok', false, 'error', 'Пароль должен быть минимум 4 символа');
  end if;
  if exists (select 1 from public.profiles where nick_lower = lower(v_nick)) then
    return jsonb_build_object('ok', false, 'code', 'taken', 'error', 'Этот ник уже занят');
  end if;

  select code_hash into v_setup from public.setup_codes where nick = lower(v_nick);
  if v_setup is null or v_setup <> public._bl_token_hash(p_code) then
    return jsonb_build_object('ok', false, 'code', 'bad_setup', 'error', 'Неверный код администратора');
  end if;

  insert into public.profiles (nick, password_hash, role, main_admin, last_login)
  values (
    v_nick,
    extensions.crypt(p_password, extensions.gen_salt('bf', 10)),
    'admin',
    lower(v_nick) = 'kostyakosmos',
    now()
  );

  delete from public.setup_codes where nick = lower(v_nick);
  v_token := public._bl_new_session(v_nick);
  insert into public.action_log (by_nick, action, target)
  values (v_nick, 'register', v_nick);

  return jsonb_build_object('ok', true, 'token', v_token, 'profile', public._bl_profile(v_nick));
end;
$$;

create or replace function public.bl_register(p_nick text, p_password text)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_nick  text := btrim(coalesce(p_nick, ''));
  v_token text;
  v_fixed boolean := public._bl_fixed_admin(v_nick);
begin
  if v_nick !~ '^[A-Za-z0-9_]{3,16}$' then
    return jsonb_build_object('ok', false, 'error', 'Ник: 3–16 символов (латиница, цифры, _)');
  end if;
  if length(coalesce(p_password, '')) < 4 then
    return jsonb_build_object('ok', false, 'error', 'Пароль должен быть минимум 4 символа');
  end if;
  if exists (select 1 from public.profiles where nick_lower = lower(v_nick)) then
    return jsonb_build_object('ok', false, 'code', 'taken', 'error', 'Этот ник уже занят');
  end if;
  if v_fixed then
    return jsonb_build_object('ok', false, 'code', 'reserved',
      'error', 'Этот ник зарезервирован — нужен код администратора');
  end if;

  begin
    insert into public.profiles (nick, password_hash, role, main_admin, last_login)
    values (
      v_nick,
      extensions.crypt(p_password, extensions.gen_salt('bf', 10)),
      'player',
      false,
      now()
    );
  exception when unique_violation then
    return jsonb_build_object('ok', false, 'code', 'taken', 'error', 'Этот ник уже занят');
  end;

  v_token := public._bl_new_session(v_nick);
  insert into public.action_log (by_nick, action, target)
  values (v_nick, 'register', v_nick);

  return jsonb_build_object('ok', true, 'token', v_token, 'profile', public._bl_profile(v_nick));
end;
$$;

create or replace function public.bl_login(p_nick text, p_password text)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_profile public.profiles%rowtype;
  v_token   text;
begin
  select * into v_profile
  from public.profiles
  where nick_lower = lower(btrim(coalesce(p_nick, '')));

  if not found then
    return jsonb_build_object('ok', false, 'code', 'not_found', 'error', 'Аккаунт не найден');
  end if;

  if v_profile.password_hash <> extensions.crypt(coalesce(p_password, ''), v_profile.password_hash) then
    return jsonb_build_object('ok', false, 'code', 'bad_password', 'error', 'Неверный пароль');
  end if;

  if v_profile.banned then
    return jsonb_build_object(
      'ok', false, 'code', 'banned',
      'error', 'Аккаунт забанен: ' || coalesce(v_profile.ban_reason, 'без причины')
    );
  end if;

  update public.profiles set last_login = now(), password_hash = extensions.crypt(p_password, extensions.gen_salt('bf', 10))
  where nick = v_profile.nick;

  v_token := public._bl_new_session(v_profile.nick);
  return jsonb_build_object('ok', true, 'token', v_token, 'profile', public._bl_profile(v_profile.nick));
end;
$$;

create or replace function public.bl_me(p_token text)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_nick text := public._bl_session_nick(p_token);
begin
  if v_nick is null then
    return jsonb_build_object('ok', false, 'error', 'Сессия истекла');
  end if;
  return jsonb_build_object('ok', true, 'profile', public._bl_profile(v_nick));
end;
$$;

create or replace function public.bl_logout(p_token text)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  delete from public.sessions where token_hash = public._bl_token_hash(coalesce(p_token, ''));
  return jsonb_build_object('ok', true);
end;
$$;

-- ---------- код для лаунчера ----------

create or replace function public.bl_create_launcher_code(p_token text)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_nick text := public._bl_session_nick(p_token);
  v_profile public.profiles%rowtype;
  v_code text;
begin
  if v_nick is null then
    return jsonb_build_object('ok', false, 'error', 'Сессия истекла — войди заново');
  end if;

  select * into v_profile from public.profiles where nick = v_nick;
  if v_profile.banned then
    return jsonb_build_object('ok', false, 'error', 'Аккаунт забанен: ' || coalesce(v_profile.ban_reason, 'без причины'));
  end if;

  delete from public.launcher_codes where expires_at < now() - interval '1 day';
  v_code := 'BLS2.' || encode(extensions.gen_random_bytes(18), 'hex');

  insert into public.launcher_codes (code_hash, nick, expires_at)
  values (public._bl_token_hash(v_code), v_nick, now() + interval '7 days');

  return jsonb_build_object('ok', true, 'code', v_code, 'expires_in', '7 дней');
end;
$$;

create or replace function public.bl_redeem_launcher_code(p_code text)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_code text := btrim(coalesce(p_code, ''));
  v_nick text;
  v_profile public.profiles%rowtype;
begin
  select c.nick into v_nick
  from public.launcher_codes c
  where c.code_hash = public._bl_token_hash(v_code)
    and c.used_at is null
    and c.expires_at > now();

  if v_nick is null then
    return jsonb_build_object('ok', false, 'error', 'Код недействителен или уже использован');
  end if;

  update public.launcher_codes set used_at = now()
  where code_hash = public._bl_token_hash(v_code);

  select * into v_profile from public.profiles where nick = v_nick;
  if v_profile.banned then
    return jsonb_build_object('ok', false, 'code', 'banned',
      'error', 'Аккаунт забанен: ' || coalesce(v_profile.ban_reason, 'без причины'));
  end if;

  insert into public.action_log (by_nick, action, target)
  values (v_nick, 'launcher_login', v_nick);

  return jsonb_build_object('ok', true, 'profile', public._bl_profile(v_nick));
end;
$$;

create or replace function public.bl_account_status(p_nick text)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_profile public.profiles%rowtype;
begin
  select * into v_profile from public.profiles
  where nick_lower = lower(btrim(coalesce(p_nick, '')));

  if not found then
    return jsonb_build_object('ok', false, 'error', 'not_found');
  end if;

  return jsonb_build_object(
    'ok', true,
    'nick', v_profile.nick,
    'role', v_profile.role,
    'main', v_profile.main_admin,
    'banned', v_profile.banned,
    'banReason', coalesce(v_profile.ban_reason, ''),
    'muted', v_profile.muted,
    'muteReason', coalesce(v_profile.mute_reason, '')
  );
end;
$$;

-- ---------- админ-панель ----------

create or replace function public.bl_admin_data(p_token text, p_search text default '')
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_admin text := public._bl_session_nick(p_token);
  v_search text := lower(btrim(coalesce(p_search, '')));
  v_players jsonb;
  v_log jsonb;
  v_total int;
  v_admins int;
  v_bans int;
  v_mutes int;
begin
  if v_admin is null or not exists (
    select 1 from public.profiles where nick = v_admin and role = 'admin'
  ) then
    return jsonb_build_object('ok', false, 'error', 'Нет доступа');
  end if;

  select coalesce(jsonb_agg(public._bl_profile(p.nick) order by
           case when p.main_admin then 0 when p.role = 'admin' then 1 else 2 end,
           lower(p.nick)), '[]'::jsonb)
  into v_players
  from public.profiles p
  where v_search = '' or p.nick_lower like '%' || v_search || '%';

  select count(*),
         count(*) filter (where role = 'admin'),
         count(*) filter (where banned),
         count(*) filter (where muted)
  into v_total, v_admins, v_bans, v_mutes
  from public.profiles;

  select coalesce(jsonb_agg(jsonb_build_object(
           'at', to_char(l.at at time zone 'Europe/Moscow', 'DD.MM.YYYY HH24:MI'),
           'by', l.by_nick,
           'action', l.action,
           'nick', coalesce(l.target, ''),
           'extra', coalesce(l.extra, '')
         ) order by l.at desc), '[]'::jsonb)
  into v_log
  from (
    select * from public.action_log order by at desc limit 60
  ) l;

  return jsonb_build_object(
    'ok', true,
    'players', v_players,
    'stats', jsonb_build_object('total', v_total, 'admins', v_admins, 'bans', v_bans, 'mutes', v_mutes),
    'log', v_log
  );
end;
$$;

create or replace function public.bl_admin_action(
  p_token text,
  p_action text,
  p_target text,
  p_extra text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_admin text := public._bl_session_nick(p_token);
  v_target text;
  v_action text := lower(btrim(coalesce(p_action, '')));
  v_extra text := left(btrim(coalesce(p_extra, '')), 200);
  v_fixed boolean;
  v_self boolean;
begin
  if v_admin is null or not exists (
    select 1 from public.profiles where nick = v_admin and role = 'admin'
  ) then
    return jsonb_build_object('ok', false, 'error', 'Нет доступа');
  end if;

  select nick into v_target from public.profiles
  where nick_lower = lower(btrim(coalesce(p_target, '')));

  if v_target is null then
    return jsonb_build_object('ok', false, 'error', 'Аккаунт не найден');
  end if;

  v_fixed := public._bl_fixed_admin(v_target);
  v_self := lower(v_target) = lower(v_admin);

  if v_action in ('ban', 'mute', 'promote', 'demote', 'delete') and (v_fixed or v_self) then
    return jsonb_build_object('ok', false, 'error', 'Этот аккаунт защищён');
  end if;

  if v_action = 'ban' then
    update public.profiles
    set banned = true, ban_reason = coalesce(nullif(v_extra, ''), 'без причины'),
        banned_at = now(), banned_by = v_admin
    where nick = v_target;
    delete from public.sessions where nick = v_target;
  elsif v_action = 'unban' then
    update public.profiles
    set banned = false, ban_reason = null, banned_at = null, banned_by = null
    where nick = v_target;
  elsif v_action = 'mute' then
    update public.profiles
    set muted = true, mute_reason = coalesce(nullif(v_extra, ''), 'без причины'),
        muted_at = now(), muted_by = v_admin
    where nick = v_target;
  elsif v_action = 'unmute' then
    update public.profiles
    set muted = false, mute_reason = null, muted_at = null, muted_by = null
    where nick = v_target;
  elsif v_action = 'promote' then
    update public.profiles set role = 'admin', main_admin = false where nick = v_target;
  elsif v_action = 'demote' then
    update public.profiles set role = 'player', main_admin = false where nick = v_target;
  elsif v_action = 'delete' then
    delete from public.profiles where nick = v_target;
  else
    return jsonb_build_object('ok', false, 'error', 'Неизвестное действие');
  end if;

  insert into public.action_log (by_nick, action, target, extra)
  values (v_admin, v_action, v_target, v_extra);

  return jsonb_build_object('ok', true);
end;
$$;

-- ---------- доступ ----------

revoke all on public.profiles, public.sessions, public.launcher_codes, public.action_log, public.setup_codes
  from public, anon, authenticated;
revoke all on sequence public.action_log_id_seq from public, anon, authenticated;

alter table public.profiles enable row level security;
alter table public.sessions enable row level security;
alter table public.launcher_codes enable row level security;
alter table public.action_log enable row level security;
alter table public.setup_codes enable row level security;

revoke all on function public._bl_token_hash(text) from public, anon, authenticated;
revoke all on function public._bl_fixed_admin(text) from public, anon, authenticated;
revoke all on function public._bl_profile(text) from public, anon, authenticated;
revoke all on function public._bl_session_nick(text) from public, anon, authenticated;
revoke all on function public._bl_new_session(text) from public, anon, authenticated;

revoke all on function public.bl_register(text, text) from public, authenticated;
revoke all on function public.bl_claim_fixed_admin(text, text, text) from public, authenticated;
revoke all on function public.bl_login(text, text) from public, authenticated;
revoke all on function public.bl_me(text) from public, authenticated;
revoke all on function public.bl_logout(text) from public, authenticated;
revoke all on function public.bl_create_launcher_code(text) from public, authenticated;
revoke all on function public.bl_redeem_launcher_code(text) from public, authenticated;
revoke all on function public.bl_account_status(text) from public, authenticated;
revoke all on function public.bl_admin_data(text, text) from public, authenticated;
revoke all on function public.bl_admin_action(text, text, text, text) from public, authenticated;

grant execute on function public.bl_register(text, text) to anon;
grant execute on function public.bl_claim_fixed_admin(text, text, text) to anon;
grant execute on function public.bl_login(text, text) to anon;
grant execute on function public.bl_me(text) to anon;
grant execute on function public.bl_logout(text) to anon;
grant execute on function public.bl_create_launcher_code(text) to anon;
grant execute on function public.bl_redeem_launcher_code(text) to anon;
grant execute on function public.bl_account_status(text) to anon;
grant execute on function public.bl_admin_data(text, text) to anon;
grant execute on function public.bl_admin_action(text, text, text, text) to anon;
