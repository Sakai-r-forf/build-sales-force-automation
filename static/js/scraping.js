(() => {
 const form=document.getElementById('crawl-form'),status=document.getElementById('crawl-status'),button=form.querySelector('button[type="submit"]');
 form.addEventListener('submit',async event=>{
  event.preventDefault();button.disabled=true;status.textContent='企業情報を取得・保存しています。画面を閉じずにお待ちください。';
  try {
   const response=await fetch(form.action,{method:'POST',body:new FormData(form),headers:{'X-Requested-With':'fetch'}});
   if(!response.ok){const result=await response.json();throw new Error(result.error||'処理に失敗しました。');}
   const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');
   link.href=url;link.download='companies.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
   status.textContent=`${response.headers.get('X-Saved-Count')}社を保存しました。企業情報一覧で送信対象を選択できます。`+(response.headers.get('X-Crawl-Partial')==='true'?'上限に達したため、取得できた分を保存しました。':'');
  }catch(error){status.textContent=error.message;}finally{button.disabled=false;}
 });
})();
