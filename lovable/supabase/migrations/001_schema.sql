-- 內容工作台（台灣版）資料表。在 Lovable Cloud 第一次建專案時整段執行。
-- 只有 members 名單裡的 Email 能讀寫（團隊內部工具）；執行前把最下面的 Email 換成你自己的。

create table if not exists public.members (
  email text primary key,
  role text not null default 'member' check (role in ('admin', 'member')),
  created_at timestamptz not null default now()
);

create or replace function public.is_member() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.members where lower(email) = lower(coalesce(auth.jwt() ->> 'email', '')));
$$;

create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.members where lower(email) = lower(coalesce(auth.jwt() ->> 'email', '')) and role = 'admin');
$$;

-- Threads 熱門話題日報：一場掃描一筆（A1 = Google 搜尋趨勢，A2 = Threads）
create table if not exists public.trend_scans (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('A1', 'A2')),
  scan_date date not null,
  scan_time text not null default '',          -- 'HH:MM'，原文缺時間就留空
  summary jsonb not null default '{}'::jsonb,  -- ▌數據摘要
  notes text[] not null default '{}',          -- ▌方法備註等
  source text not null default 'import' check (source in ('import', 'auto', 'manual')),
  created_by uuid default auth.uid(),
  created_at timestamptz not null default now(),
  unique (kind, scan_date, scan_time)
);

create table if not exists public.trend_terms (          -- A1 熱搜詞
  id uuid primary key default gen_random_uuid(),
  scan_id uuid not null references public.trend_scans(id) on delete cascade,
  rank int not null,
  term text not null,
  traffic text not null default '',
  traffic_n int,
  category text not null default ''
);
create index if not exists trend_terms_term_idx on public.trend_terms (lower(term));

create table if not exists public.threads_topics (       -- A2 趨勢話題
  id uuid primary key default gen_random_uuid(),
  scan_id uuid not null references public.trend_scans(id) on delete cascade,
  no int not null,
  title text not null,
  volume text not null default '',
  volume_n int,
  summary text not null default ''
);

create table if not exists public.threads_posts (        -- A2 貼文（topic_id 為空 = For You 動態牆精選）
  id uuid primary key default gen_random_uuid(),
  scan_id uuid not null references public.trend_scans(id) on delete cascade,
  topic_id uuid references public.threads_topics(id) on delete cascade,
  ord int not null default 0,
  author text not null default '',
  content text not null default '',
  likes int, replies int, reposts int, shares int,
  url text not null default '',
  comments jsonb not null default '[]'::jsonb      -- [{author, text, likes}]
);
create index if not exists threads_posts_scan_idx on public.threads_posts (scan_id);

create table if not exists public.ideas (                -- 選題庫
  id uuid primary key default gen_random_uuid(),
  title text not null,
  source text not null default '',
  note text not null default '',
  status text not null default 'pending' check (status in ('pending', 'doing', 'done', 'dropped')),
  created_by uuid default auth.uid(),
  created_at timestamptz not null default now()
);

create table if not exists public.schedule_items (       -- 內容日曆
  id uuid primary key default gen_random_uuid(),
  title text not null,
  date date not null,
  time text not null default '',
  platform text not null default '',
  status text not null default 'draft' check (status in ('idea', 'draft', 'scheduled', 'published')),
  note text not null default '',
  draft_id uuid,
  created_by uuid default auth.uid(),
  created_at timestamptz not null default now()
);

create table if not exists public.drafts (               -- 發布中心草稿與 AI 改寫結果
  id uuid primary key default gen_random_uuid(),
  title text not null default '',
  body text not null default '',
  tags text not null default '',
  platforms text[] not null default '{}',
  outputs jsonb not null default '{}'::jsonb,     -- {"instagram": "...", "threads": "..."}
  created_by uuid default auth.uid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.ai_usage (             -- 每次呼叫 Claude 的用量與費用（由 ai 函式寫入）
  id uuid primary key default gen_random_uuid(),
  feature text not null,
  model text not null,
  input_tokens int not null default 0,
  output_tokens int not null default 0,
  cache_read_tokens int not null default 0,
  cost_usd numeric(10, 5) not null default 0,
  created_by uuid,
  created_at timestamptz not null default now()
);

-- 權限：全部表只有成員能用；members 只有管理員能改
do $$
declare t text;
begin
  foreach t in array array['trend_scans','trend_terms','threads_topics','threads_posts','ideas','schedule_items','drafts'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists member_all on public.%I', t);
    execute format('create policy member_all on public.%I for all to authenticated using (public.is_member()) with check (public.is_member())', t);
  end loop;
end $$;

alter table public.ai_usage enable row level security;
drop policy if exists member_read on public.ai_usage;
create policy member_read on public.ai_usage for select to authenticated using (public.is_member());

alter table public.members enable row level security;
drop policy if exists member_read on public.members;
create policy member_read on public.members for select to authenticated using (public.is_member());
drop policy if exists admin_write on public.members;
create policy admin_write on public.members for all to authenticated using (public.is_admin()) with check (public.is_admin());

-- 本月 AI 花費（工作台與設定頁用）
create or replace view public.ai_usage_month with (security_invoker = true) as
  select coalesce(sum(cost_usd), 0)::numeric(10, 2) as cost_usd, count(*) as calls
  from public.ai_usage
  where created_at >= date_trunc('month', now() at time zone 'Asia/Taipei') at time zone 'Asia/Taipei';

-- ⚠️ 換成你自己的 Email（第一位管理員）。之後在「設定 → 成員」新增同事。
insert into public.members (email, role) values ('YOUR_EMAIL@example.com', 'admin') on conflict (email) do nothing;
