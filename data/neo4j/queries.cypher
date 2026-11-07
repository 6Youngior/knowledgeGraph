// Run import.cypher first. These are example queries for a Neo4j deployment.
// The delivered local dashboard itself runs the corresponding NetworkX queries.

// Direct developer / issuer path; relationship direction is factual.
MATCH p=(e:Event)-[:RELEASED_MODEL]->(m:Model)-[:DEVELOPED_BY]->(c:Company)-[:LISTED_AS]->(s:Stock)
WHERE e.id = 'event:glm5-release'
RETURN p;

// Product adaptation path, traversing two factual edges in reverse.
MATCH p=(e:Event)-[:RELEASED_MODEL]->(m:Model)<-[:SUPPORTS_MODEL]-(gpu:Product)<-[:PRODUCES]-(c:Company)-[:LISTED_AS]->(s:Stock)
WHERE e.id = 'event:glm5-release'
RETURN p;

// Cloud distribution is a separate predicate and semantic group.
MATCH p=(e:Event)-[:RELEASED_MODEL]->(m:Model)<-[:HOSTS_MODEL]-(cloud:Product)<-[:PRODUCES]-(c:Company)-[:LISTED_AS]->(s:Stock)
WHERE e.id = 'event:glm5-release'
RETURN p;

// Historical disclosure filter. Facts with unknown disclosure are excluded.
MATCH (a:Entity)-[r]->(b:Entity)
WHERE r.disclosed_at IS NOT NULL AND r.disclosed_at <> '' AND r.disclosed_at <= '2026-02-12'
RETURN a, r, b;
