(() => {
  const searchInput = document.getElementById('search-input');
  const search = () => { const params = new URLSearchParams({search:searchInput.value.trim()}); location.href = '/companies/?'+params; };
  document.getElementById('search-btn').addEventListener('click', search);
  searchInput.addEventListener('keydown', e => {if(e.key === 'Enter') {e.preventDefault();search();}});
  document.querySelectorAll('td.companyName').forEach(td => {
    const raw=td.textContent.trim(); td.title=raw; td.textContent='';
    const chars=Array.from(raw); td.append(document.createTextNode(chars.slice(0,10).join('')));
    if(chars.length>10) {td.append(document.createElement('br'), document.createTextNode(chars.slice(10,20).join('')+(chars.length>20?'…':'')));}
  });
  document.querySelectorAll('td.companySite a,td.inquiryUrl a').forEach(a=>{const raw=a.textContent.trim();a.title=raw;a.textContent=raw.length>15?raw.slice(0,15)+'…':raw;a.rel='noopener noreferrer';});
  document.getElementById('pageTopBtn').addEventListener('click',()=>scrollTo({top:0,behavior:'smooth'}));
  const token = document.querySelector('meta[name="csrf-token"]').content;
  const dialog=document.getElementById('delivery-dialog'), form=document.getElementById('delivery-form');
  const status=document.getElementById('delivery-status'), send=document.getElementById('delivery-send'), save=document.getElementById('delivery-save'), close=document.getElementById('delivery-close'), stop=document.getElementById('delivery-stop');
  let running=false,stopped=false;
  const selected = () => [...document.querySelectorAll('.delivery-select:checked')];
  document.getElementById('select-all').addEventListener('change',event=>document.querySelectorAll('.delivery-select').forEach(c=>c.checked=event.target.checked));
  const api=async(url,data)=>{
    const response=await fetch(url,{method:data?'POST':'GET',headers:{'Content-Type':'application/json','X-CSRF-Token':token},body:data?JSON.stringify(data):undefined});
    const result=await response.json(); if(!response.ok) throw new Error(result.error||result.message||'処理に失敗しました。画面を再読み込みしてください。');return result;
  };
  const refreshTargets=()=>{
    const list=document.getElementById('delivery-targets');list.textContent='';
    selected().forEach(c=>{const li=document.createElement('li');li.textContent=c.closest('tr').querySelector('.companyName').title;list.append(li);});
    document.getElementById('delivery-count').textContent=selected().length;
    send.disabled=!selected().length;
  };
  document.getElementById('delivery-open').addEventListener('click',async()=>{
    status.textContent='下書きを読み込んでいます…';refreshTargets();dialog.showModal();
    try {const settings=await api('/deliveries/settings');Object.entries(settings).forEach(([key,value])=>{if(form.elements.namedItem(key))form.elements.namedItem(key).value=value;});status.textContent='';}
    catch(error){status.textContent=error.message;send.disabled=true;}
  });
  close.addEventListener('click',()=>dialog.close());
  dialog.addEventListener('cancel',event=>{if(running)event.preventDefault();});
  stop.addEventListener('click',()=>{stopped=true;stop.disabled=true;});
  save.addEventListener('click',async()=>{
    if(!form.reportValidity())return;save.disabled=true;
    try {await api('/deliveries/settings',Object.fromEntries(new FormData(form)));status.textContent='下書きを保存しました。';}
    catch(error){status.textContent=error.message;}finally{save.disabled=false;}
  });
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(running)return;
    const targets=selected(); if(!targets.length)return;
    const payload=Object.fromEntries(new FormData(form));
    if(!confirm(`${targets.length}社のお問い合わせフォームへ、表示中の内容を送信します。よろしいですか？`))return;
    running=true;stopped=false;send.disabled=true;save.disabled=true;close.disabled=true;stop.hidden=false;stop.disabled=false;
    const messages=[];
    for(let index=0;index<targets.length&&!stopped;index++){
      const checkbox=targets[index],name=checkbox.closest('tr').querySelector('.companyName').title;
      status.textContent=`${index+1}/${targets.length}社：${name} を処理しています。\n`+messages.join('\n');
      try {
        const result=await api(`/deliveries/${checkbox.value}/send`,payload);
        messages.push(`${name}：${result.message}`);
        const labels={sent:'✓ 送信済',unknown:'要確認',manual_required:'手動対応',failed:'接続失敗'};
        const cell=checkbox.closest('td');cell.title=result.message;
        if(['sent','unknown','sending'].includes(result.status)){cell.textContent=labels[result.status]||'要確認';}
        else {checkbox.checked=false;cell.querySelector('span').textContent=labels[result.status]||'未送信';}
      } catch(error){messages.push(`${name}：${error.message} 再送せず画面を再読み込みして結果を確認してください。`);stopped=true;}
    }
    status.textContent=(stopped?'停止しました。':'処理が完了しました。')+'\n'+messages.join('\n');
    document.getElementById('delivery-summary').textContent='送信結果を更新しました。';
    running=false;save.disabled=false;close.disabled=false;stop.hidden=true;refreshTargets();
  });
  addEventListener('beforeunload',event=>{if(running){event.preventDefault();event.returnValue='';}});
})();
