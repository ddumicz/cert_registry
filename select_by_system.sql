
SELECT DISTINCT s.asset_name AS system_name, a.asset_name AS asset_name,
       a.ip_address, c.subject, c.sha256, c.valid_to
FROM cert_registry.assets s
JOIN cert_registry.asset_relations ar ON ar.parent_asset_id = s.id
JOIN cert_registry.assets a ON a.id = ar.child_asset_id
JOIN cert_registry.certificate_assets ca ON ca.asset_id = a.id
JOIN cert_registry.certificates c ON c.id = ca.certificate_id
---WHERE s.asset_type = 'SYSTEM' --- AND s.asset_key = 'SYS-001'
ORDER BY a.ip_address, c.valid_to;
