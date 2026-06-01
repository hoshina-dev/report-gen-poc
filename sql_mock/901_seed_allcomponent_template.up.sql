INSERT INTO experiment_templates (id, name)
VALUES ('b928e91f-7f46-43df-b776-b1aaa7482812', 'All Input Types Showcase')
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, updated_at = NOW();

INSERT INTO pdf_templates (exp_tmpl_id, components)
VALUES ('b928e91f-7f46-43df-b776-b1aaa7482812', '[]'::jsonb)
ON CONFLICT (exp_tmpl_id) DO UPDATE SET
    components = EXCLUDED.components,
    updated_at = NOW();
