<?php
/**
 * Optional capability probe for the pure-web player (config.js endpoints.ping).
 * Plain static hosts answer 404 and the player simply stays in pure-web mode.
 */
header('Content-Type: application/json');
echo json_encode(['ok' => true, 'pure' => true]);
