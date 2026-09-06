(() => {
 const select=document.getElementById('saved-source'),name=document.getElementById('source-name'),url=document.getElementById('seed-url');
 const save=document.getElementById('source-save'),remove=document.getElementById('source-delete'),status=document.getElementById('source-status');
 const token=document.querySelector('meta[name="csrf-token"]').content;
 let sources=[];
 async function api(path='',options={}) {
  const response=await fetch('/scraping/sources'+path,{...options,headers:{'Content-Type':'application/json','X-CSRF-Token':token,'X-Requested-With':'fetch'}});
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(data.error||'登録情報の処理に失敗しました。時間をおいて再度お試しください。');
  return data;
 }
 async function refresh(id='') {
  sources=(await api()).sources;
  select.replaceChildren(new Option('URLを選択してください',''));
  sources.forEach(source=>select.add(new Option(`${source.name} — ${source.url}`,source.id)));
  select.value=id;remove.disabled=!select.value;
 }
 select.addEventListener('change',()=>{
  const source=sources.find(item=>item.id===select.value);
  if(source){name.value=source.name;url.value=source.url;status.textContent='登録済みURLを選択しました。「CSVを生成」で取得を開始します。';}
  remove.disabled=!source;
 });
 save.addEventListener('click',async()=>{
  save.disabled=true;remove.disabled=true;
  try {
   const data=await api('',{method:'POST',body:JSON.stringify({name:name.value,url:url.value})});
   await refresh(data.source.id);status.textContent='スクレイピング先を保存しました。';
  }catch(error){status.textContent=error.message;}finally{save.disabled=false;remove.disabled=!select.value;}
 });
 remove.addEventListener('click',async()=>{
  const source=sources.find(item=>item.id===select.value);
  if(!source||!window.confirm(`「${source.name}」のURL登録を削除しますか？`))return;
  save.disabled=true;remove.disabled=true;
  try {
   await api('/'+encodeURIComponent(source.id),{method:'DELETE'});
   await refresh();status.textContent='URL登録を削除しました。取得済みの企業情報は残ります。';
  }catch(error){status.textContent=error.message;}finally{save.disabled=false;remove.disabled=!select.value;}
 });
 refresh().catch(error=>{status.textContent=error.message;});
})();
