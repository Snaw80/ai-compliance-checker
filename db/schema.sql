-- AI Act assistant: corpus schema.
-- Runs automatically on first `docker compose up` (docker-entrypoint-initdb.d).

create extension if not exists vector;

-- One row per source document (a regulation, a guideline PDF, an FAQ page set).
create table if not exists documents (
  doc_id         text primary key,                 -- e.g. 'eu-ai-act-consolidated'
  title          text not null,
  jurisdiction   text not null,                    -- 'EU' or ISO-3166 alpha-2 ('FR', 'FI', 'NO', ...)
  doc_type       text not null check (doc_type in (
                   'regulation', 'amending_regulation', 'guideline', 'code_of_practice',
                   'national_law', 'authority_guidance', 'consultation', 'faq')),
  status         text not null check (status in (
                   'in_force', 'final', 'draft', 'consultation', 'superseded')),
  binding        boolean not null,
  language       text not null,                    -- ISO-639-1
  published      date,
  version_date   date,                             -- e.g. consolidation date
  url            text not null,
  retrieved_at   timestamptz not null default now(),
  corpus_version text not null
);

-- One row per retrievable unit (article paragraph, definition, recital, guideline paragraph, FAQ item).
create table if not exists chunks (
  chunk_id       text primary key,                 -- stable, human-readable: 'eu-ai-act-consolidated:art_50:1'
  doc_id         text not null references documents (doc_id) on delete cascade,
  seq            integer not null,                 -- order inside the document
  article_ref    text,                             -- display/citation label: 'Art. 50(1)', 'Annex III point 4', 'Recital 132'
  title          text,                             -- article / section title
  context        text not null,                    -- contextual header prepended before embedding
  text           text not null,
  refs           text[] not null default '{}',     -- cross-references: {'Art. 6(2)', 'Annex III'}
  amended_by     text,                             -- e.g. 'Regulation (EU) 2026/1744' when the text comes from an amendment
  url            text not null,                    -- deep link (with anchor when available)
  embedding      vector(1024),                     -- BGE-M3 dense (filled on day 2)
  tsv            tsvector generated always as (
                   setweight(to_tsvector('english', coalesce(article_ref, '') || ' ' || coalesce(title, '')), 'A') ||
                   setweight(to_tsvector('english', text), 'B')
                 ) stored,
  unique (doc_id, seq)
);

create index if not exists chunks_doc_id_idx      on chunks (doc_id);
create index if not exists chunks_article_ref_idx on chunks (article_ref);
create index if not exists chunks_refs_idx        on chunks using gin (refs);
create index if not exists chunks_tsv_idx         on chunks using gin (tsv);
create index if not exists chunks_embedding_idx   on chunks using hnsw (embedding vector_cosine_ops);
