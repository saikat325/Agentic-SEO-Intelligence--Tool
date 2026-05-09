import axios from 'axios';

const API = axios.create({ baseURL: 'http://localhost:8000' });


export const ingestRepo = (github_url) =>
  API.post('/ingest', { github_url }).then(r => r.data);

export const getStatus = (repo_id) =>
  API.get(`/status/${repo_id}`).then(r => r.data);

export const queryRepo = (repo_id, query) =>
  API.post('/query', { repo_id, query }).then(r => r.data);

export const rawSearch = (repo_id, q, top_k = 5) =>
  API.get(`/search/${repo_id}`, { params: { q, top_k } }).then(r => r.data);

export const listRepos = () =>
  API.get('/repos').then(r => r.data);
