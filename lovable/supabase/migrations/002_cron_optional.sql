-- （選用）每天 10:00／15:00／21:00（台北時間）自動存一場 A1（Google 搜尋趨勢台灣 TOP 20）並用 AI 補分類。
-- 執行前替換三個值：
--   <PROJECT_REF>   專案網址 https://<PROJECT_REF>.supabase.co 的那一段
--   <ANON_KEY>      專案的 anon／publishable key（本來就公開在前端，函式閘道器需要它）
--   <CRON_SECRET>   自己想一串長亂碼，同一串也要加到 Secrets 的 CRON_SECRET
-- Lovable Cloud 若不允許 pg_cron／pg_net，就略過這一步，改用頁面上的「立即存一場 A1」按鈕。
create extension if not exists pg_cron;
create extension if not exists pg_net;

do $$
declare
  slot record;
begin
  for slot in select * from (values ('a1-1000', '0 2 * * *'), ('a1-1500', '0 7 * * *'), ('a1-2100', '0 13 * * *')) as v(name, cron) loop
    perform cron.unschedule(slot.name) where exists (select 1 from cron.job where jobname = slot.name);
    perform cron.schedule(slot.name, slot.cron, $job$
      select net.http_post(
        url := 'https://<PROJECT_REF>.supabase.co/functions/v1/tw-trends',
        headers := jsonb_build_object('Content-Type', 'application/json',
                                      'Authorization', 'Bearer <ANON_KEY>',
                                      'x-cron-secret', '<CRON_SECRET>'),
        body := '{"action": "save_a1", "classify": true}'::jsonb
      );
    $job$);
  end loop;
end $$;
