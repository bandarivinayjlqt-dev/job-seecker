import axios from 'axios';
const api=axios.create({baseURL:import.meta.env.VITE_API_URL||'http://localhost:8000/api'});
export const token=()=>localStorage.getItem('jobhub_token')||'';
api.interceptors.request.use(c=>{if(token())c.headers.Authorization=`Bearer ${token()}`;return c});
export const A={register:x=>api.post('/auth/register',x).then(r=>r.data),login:x=>api.post('/auth/login',x).then(r=>r.data),profile:()=>api.get('/profile').then(r=>r.data),upload:f=>{let d=new FormData();d.append('file',f);return api.post('/profile/resume',d).then(r=>r.data)},jobs:p=>api.get('/jobs',{params:p}).then(r=>r.data),job:id=>api.get('/jobs/'+id).then(r=>r.data),save:id=>api.post(`/jobs/${id}/save`).then(r=>r.data),saved:()=>api.get('/jobs/saved/me').then(r=>r.data),recs:()=>api.get('/jobs/recommendations/me').then(r=>r.data),chat:m=>api.post('/chat',{message:m}).then(r=>r.data),stats:()=>api.get('/admin/stats').then(r=>r.data),sources:()=>api.get('/admin/sources').then(r=>r.data)};
