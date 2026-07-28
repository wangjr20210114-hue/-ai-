import test from 'node:test';
import assert from 'node:assert/strict';
import { __test } from './index.js';

const {
  downloadFirstValidPdf,
  extractArxivId,
  extractDoi,
  findReusablePaper,
  isSafePublicHttps,
  resolveDownloadCandidates,
  titleMatches,
} = __test;

test('reuses only an exact stored paper identity', () => {
  const items = [
    { id: 'arxiv', arxiv_id: '2601.01234', source_url: 'https://arxiv.org/abs/2601.01234' },
    { id: 'doi', arxiv_id: '', source_url: 'https://doi.org/10.1145/3808169' },
  ];
  assert.equal(findReusablePaper(items, {
    arxivId: '2601.01234',
    sourceUrl: '',
    directPdf: '',
  })?.id, 'arxiv');
  assert.equal(findReusablePaper(items, {
    arxivId: 'webpaper-demo',
    sourceUrl: 'https://doi.org/10.1145/3808169',
    directPdf: '',
  })?.id, 'doi');
  assert.equal(findReusablePaper(items, {
    arxivId: '2601.99999',
    sourceUrl: '',
    directPdf: '',
  }), undefined);
});

test('extracts canonical scholarly identifiers without accepting private URLs', () => {
  assert.equal(extractDoi('https://doi.org/10.1145/3808169'), '10.1145/3808169');
  assert.equal(extractArxivId('https://arxiv.org/pdf/2601.01234v2.pdf'), '2601.01234v2');
  assert.equal(isSafePublicHttps('https://papers.example/article.pdf'), true);
  assert.equal(isSafePublicHttps('http://papers.example/article.pdf'), false);
  assert.equal(isSafePublicHttps('https://127.0.0.1/article.pdf'), false);
});

test('matches exact scholarly titles while rejecting merely related titles', () => {
  assert.equal(
    titleMatches(
      'Project-Level C-to-Rust Translation via Pointer Knowledge Graphs',
      'Project-Level C-to-Rust Translation via Pointer Knowledge Graphs',
    ),
    true,
  );
  assert.equal(
    titleMatches(
      'Project-Level C-to-Rust Translation via Pointer Knowledge Graphs',
      'A Survey of Rust Translation Systems',
    ),
    false,
  );
});

test('resolves a source-only DOI card through OpenAlex public PDF metadata', async () => {
  const mockFetch = async (url) => {
    const value = String(url);
    if (value.startsWith('https://api.openalex.org/works?')) {
      return new Response(JSON.stringify({
        results: [{
          ids: {},
          best_oa_location: {
            pdf_url: 'https://repository.example/paper.pdf',
          },
          primary_location: null,
          locations: [],
        }],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    if (value.startsWith('https://api.crossref.org/works/')) {
      return new Response(JSON.stringify({ message: { link: [] } }), { status: 200 });
    }
    if (value.startsWith('https://export.arxiv.org/api/query?')) {
      return new Response('<feed></feed>', { status: 200 });
    }
    throw new Error(`Unexpected URL: ${value}`);
  };

  const candidates = await resolveDownloadCandidates({
    arxivId: 'webpaper-demo',
    directPdf: '',
    sourceUrl: 'https://doi.org/10.1145/3808169',
    title: 'Project-Level C-to-Rust Translation via Pointer Knowledge Graphs',
  }, mockFetch);

  assert.deepEqual(candidates, [{
    url: 'https://repository.example/paper.pdf',
    arxivId: '',
    source: 'OpenAlex',
  }]);
});

test('uses an exact-title arXiv result when a DOI has no public PDF', async () => {
  const title = 'Project-Level C-to-Rust Translation via Pointer Knowledge Graphs';
  const mockFetch = async (url) => {
    const value = String(url);
    if (value.startsWith('https://api.openalex.org/works?')) {
      return new Response(JSON.stringify({ results: [] }), { status: 200 });
    }
    if (value.startsWith('https://api.crossref.org/works/')) {
      return new Response(JSON.stringify({ message: { link: [] } }), { status: 200 });
    }
    if (value.startsWith('https://export.arxiv.org/api/query?')) {
      return new Response(
        `<feed><entry><id>https://arxiv.org/abs/2607.01234v1</id><title>${title}</title></entry></feed>`,
        { status: 200 },
      );
    }
    throw new Error(`Unexpected URL: ${value}`);
  };

  const candidates = await resolveDownloadCandidates({
    arxivId: 'webpaper-demo',
    directPdf: '',
    sourceUrl: 'https://doi.org/10.1145/3808169',
    title,
  }, mockFetch);

  assert.deepEqual(candidates, [{
    url: 'https://arxiv.org/pdf/2607.01234v1.pdf',
    arxivId: '2607.01234v1',
    source: 'arXiv title',
  }]);
});

test('skips a non-PDF candidate and accepts the next valid public PDF', async () => {
  const bytes = new Uint8Array(1200);
  bytes.set(new TextEncoder().encode('%PDF-'));
  const mockFetch = async (url) => (
    String(url).includes('not-pdf')
      ? new Response('<html>publisher page</html>', { status: 200 })
      : new Response(bytes, {
        status: 200,
        headers: { 'Content-Type': 'application/pdf', 'Content-Length': String(bytes.length) },
      })
  );

  const result = await downloadFirstValidPdf([
    { url: 'https://publisher.example/not-pdf', arxivId: '', source: 'Crossref' },
    { url: 'https://repository.example/paper.pdf', arxivId: '', source: 'OpenAlex' },
  ], mockFetch);

  assert.equal(result.data.byteLength, bytes.length);
  assert.equal(result.candidate.url, 'https://repository.example/paper.pdf');
});
