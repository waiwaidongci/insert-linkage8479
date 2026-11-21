import {feedback} from '../components/common/fields.js';
import {panel, pill} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {OP, PACK, REVIEW} from '../constants/enums.js';
import {handler} from '../hooks/action.js';
import {session} from '../stores/session.js';
import {workspace} from '../stores/workspace.js';
import {button, el, link, p} from '../utils/dom.js';
import {date} from '../utils/format.js';
import {runPage} from './run.js';

const summaryText = summary => `${OP.added} ${summary.added} · ${OP.removed} ${summary.removed} · ${OP.changed} ${summary.changed}`;
const shortHash = hash => el('code', {title:hash}, `${hash.slice(0,12)}…`);

function sitePanel(box, message, refresh) {
  const ship = box.shipment;
  const progress = ship
    ? p(`在途发货：第 ${ship.from_version} 版 → 第 ${ship.to_version} 版 · ${summaryText(ship.summary)} · 已确认 ${ship.acked}/${ship.package_count} 包`, 'subtle')
    : p(box.baseline >= box.latest_version ? '本站基线已是最新签核版，暂无待收包。' : '等待下一次派发。', 'subtle');
  const packs = !ship ? null : table([
    {label:'包号', render:row=>`第 ${row.seq} / ${ship.package_count} 包`},
    {label:'条目', render:row=>`${row.item_count} 条（${summaryText(row.summary)}）`},
    {label:'内容指纹', render:row=>shortHash(row.fingerprint)},
    {label:'状态', render:row=>pill(PACK[row.state],row.state)},
    {label:'操作', render:row=>{
      const actions = el('div',{class:'activity'});
      const download = button('下载',{class:'quiet'});
      download.addEventListener('click', handler(download,message,() =>
        workspace.download(`/procure/sites/${encodeURIComponent(box.site)}/packages/${row.seq}`,
          `备料清单-${box.site}-第${ship.from_version}版至第${ship.to_version}版-第${row.seq}包.json`)));
      actions.append(download);
      if (row.state==='pending' && session.canWrite) {
        const confirm = button('确认收讫',{class:'quiet'});
        confirm.addEventListener('click', handler(confirm,message,async()=>{
          await workspace.ack(box.site,row.seq,row.fingerprint);
          await refresh();
        }));
        actions.append(confirm);
      }
      return actions;
    }},
    {label:'回执', render:row=>row.state==='acked' ? `${row.acked_by} · ${date(row.acked_at)}` : '—'},
  ], box.packages, {caption:`${box.site} 待收包`, empty:'暂无分包。'});
  return panel(`${box.site} · 基线第 ${box.baseline} 版（最新签核第 ${box.latest_version} 版）`, progress, packs);
}

export async function deliveryPage(route, refresh) {
  const {spec, runs} = workspace;
  const message = feedback();
  const artifacts = table([
    {label:'报告', render:row=>link(row.name,`#results/${row.id}`)},
    {label:'复核', render:row=>pill(REVIEW[row.review],row.review)},
    {label:'计算时间', render:row=>date(row.finished_at)},
    {label:'下载', render:row=>{
      const download = button('下载 CSV',{class:'quiet'});
      download.addEventListener('click', handler(download,message,() =>
        workspace.download(`/runs/${row.id}/export`,`${spec.short_name}-${row.id}.csv`)));
      return download;
    }},
  ], runs.filter(row=>row.status==='complete'), {caption:'可导出的结果', empty:'完成计算后会生成对应的报告。'});
  const [versions, outboxes] = await Promise.all([
    workspace.versions(), Promise.all(spec.sites.map(site=>workspace.outbox(site)))]);
  const siteMessage = feedback();
  const versionRows = table([
    {label:'版本', render:row=>`第 ${row.version} 版`},
    {label:'来源运行', render:row=>link(`运行 ${row.run_id}`,`#results/${row.run_id}`)},
    {key:'entry_count', label:'清单条目'},
    {label:'内容指纹', render:row=>shortHash(row.fingerprint)},
    {key:'author', label:'签核人'},
    {label:'时间', render:row=>date(row.created_at)},
  ], versions, {caption:'签核版清单', empty:'复核通过首次运行后生成首个签核版。'});
  const delivery = spec.scheduled ? panel('站内分发回执', table([
    {key:'recipient',label:'收件团队'},
    {label:'回执',render:row=>pill(row.state==='delivered'?'已投递':'已拦截',row.state)},
    {key:'detail',label:'说明'}, {label:'时间',render:row=>date(row.created_at)},
    {label:'查看',render:row=>link(`运行 ${row.run_id}`,`#results/${row.run_id}`)},
  ],await workspace.deliveries(),{caption:'站内收件箱',empty:'计划到时执行，回执将在此更新。'})) : null;
  return el('div',{}, panel(spec.pages[5], p('按运行批次下载 CSV，复核状态随报告保留。','subtle'), artifacts, message),
    el('div',{class:'two-col'},
      el('div',{class:'wide-panel'}, panel('签核版本', versionRows),
        ...outboxes.map(box=>sitePanel(box,siteMessage,refresh)), siteMessage),
      el('aside',{class:'sidebar-panel'},
        panel('分发口径', el('ul',{class:'method-list'}, spec.protocol.map(text=>el('li',{},text)))))),
    delivery, spec.scheduled && await runPage({...route,scheduling:true},refresh));
}
