<?php
/** Dependency-free contracts for the real bridge with WordPress API doubles. */
require __DIR__ . '/bootstrap.php';
set_error_handler( function ( $severity, $message, $file, $line ) {
	throw new ErrorException( $message, 0, $severity, $file, $line );
} );

function ewc_assert( $condition, $message ) { if ( ! $condition ) { throw new RuntimeException( $message ); } }
function ewc_equal( $expected, $actual ) { ewc_assert( $expected === $actual, 'Expected ' . var_export( $expected, true ) . '; received ' . var_export( $actual, true ) ); }
function ewc_error( $value, $code, $status ) {
	ewc_assert( is_wp_error( $value ), 'Expected WP_Error' );
	ewc_equal( $code, $value->get_error_code() );
	ewc_equal( $status, $value->get_error_data()['status'] );
}
function ewc_providers() {
	if ( ! defined( 'WPSEO_VERSION' ) ) { define( 'WPSEO_VERSION', 'fixture-yoast' ); }
	if ( ! defined( 'RANK_MATH_VERSION' ) ) { define( 'RANK_MATH_VERSION', 'fixture-rankmath' ); }
}

if ( isset( $argv[1] ) && in_array( $argv[1], array( '--snapshot', '--download' ), true ) ) {
	ewc_providers();
	if ( '--download' === $argv[1] ) { EWebCity_SEO_Bridge::download(); }
	echo wp_json_encode( EWebCity_SEO_Bridge::snapshot(), JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES );
	exit;
}

$passed = 0;
$failed = 0;
function ewc_test( $name, $callback ) {
	global $passed, $failed;
	ewc_reset_fixture();
	try { $callback(); ++$passed; echo 'PASS ' . $name . "\n"; }
	catch ( Throwable $error ) { ++$failed; fwrite( STDERR, 'FAIL ' . $name . ': ' . $error->getMessage() . "\n" ); }
}

ewc_test( 'hooks expose no unauthenticated download handler', function () {
	ewc_equal( array( 'admin_menu', 'admin_post_ewebcity_seo_download', 'rest_api_init' ), array_keys( $GLOBALS['ewc_actions'] ) );
} );
ewc_test( 'inactive providers produce an empty metadata JSON object', function () {
	$snapshot = EWebCity_SEO_Bridge::snapshot();
	ewc_equal( array(), $snapshot['providers'] );
	ewc_equal( '{}', wp_json_encode( $snapshot['posts'][0]['metadata'] ) );
} );
ewc_test( 'capability denial occurs before any query or option read', function () {
	$GLOBALS['ewc_capable'] = false;
	ewc_equal( false, EWebCity_SEO_Bridge::can_read() );
	ewc_error( EWebCity_SEO_Bridge::snapshot(), 'ewebcity_forbidden', 403 );
	ewc_equal( array(), $GLOBALS['ewc_query_calls'] );
	ewc_equal( array(), $GLOBALS['ewc_option_reads'] );
} );
ewc_test( 'REST route is GET with an actual capability callback and bounded arguments', function () {
	EWebCity_SEO_Bridge::register_rest();
	$route = $GLOBALS['ewc_route'];
	ewc_equal( 'ewebcity/v1', $route[0] ); ewc_equal( '/snapshot', $route[1] );
	ewc_equal( 'GET', $route[2]['methods'] );
	$GLOBALS['ewc_capable'] = false;
	ewc_equal( false, call_user_func( $route[2]['permission_callback'] ) );
	ewc_equal( false, call_user_func( $route[2]['args']['per_page']['validate_callback'], '101' ) );
	ewc_equal( true, call_user_func( $route[2]['args']['page']['validate_callback'], '100' ) );
} );

ewc_providers();
ewc_test( 'only published public queryable unprotected posts are included', function () {
	$snapshot = EWebCity_SEO_Bridge::snapshot();
	ewc_equal( array( 1, 7 ), array_column( $snapshot['posts'], 'id' ) );
	ewc_equal( 2, $snapshot['pagination']['total_posts'] );
	$args = $GLOBALS['ewc_query_calls'][0];
	ewc_equal( 'ids', $args['fields'] ); ewc_equal( false, $args['has_password'] );
	ewc_equal( 'publish', $args['post_status'] ); ewc_equal( 20, $args['posts_per_page'] );
	ewc_equal( array( 'post', 'page' ), $args['post_type'] );
	ewc_equal( true, $args['suppress_filters'] );
} );
ewc_test( 'contract preserves overrides, missing versus empty, and raw canonical values', function () {
	$snapshot = EWebCity_SEO_Bridge::snapshot();
	ewc_equal( 'ewebcity-wordpress-snapshot', $snapshot['format'] );
	ewc_equal( '1.0', $snapshot['schema_version'] ); ewc_equal( '2.2.0', $snapshot['bridge_version'] );
	ewc_equal( 'Mahim', $snapshot['auditor'] ); ewc_equal( EWebCity_SEO_Bridge::SEMANTICS, $snapshot['metadata_semantics'] );
	ewc_equal( array( 'yoast', 'rankmath' ), array_column( $snapshot['providers'], 'id' ) );
	$metadata = (array) $snapshot['posts'][0]['metadata'];
	ewc_equal( '%%title%% | Example', $metadata['yoast']['title'] );
	ewc_equal( '', $metadata['yoast']['description'] ); ewc_equal( null, $metadata['yoast']['canonical'] );
	ewc_equal( '2', $metadata['yoast']['robots_noindex'] );
	ewc_equal( '/raw-relative-canonical', $metadata['rankmath']['canonical'] );
	ewc_equal( array( 'index', 'follow' ), $metadata['rankmath']['robots'] );
} );
ewc_test( 'content, author, password, private keys and unrelated options are absent', function () {
	$snapshot = EWebCity_SEO_Bridge::snapshot(); $json = wp_json_encode( $snapshot );
	foreach ( array( 'BODY_MUST_NOT_EXPORT', 'EXCERPT_MUST_NOT_EXPORT', 'PASSWORD_MUST_NOT_EXPORT', 'KEY_MUST_NOT_EXPORT', 'META_KEY_MUST_NOT_EXPORT', 'post_author', '9123' ) as $forbidden ) {
		ewc_assert( false === strpos( $json, $forbidden ), 'Leaked ' . $forbidden );
	}
	ewc_equal( array( 'permalink_structure', 'blog_public' ), $GLOBALS['ewc_option_reads'] );
	foreach ( $GLOBALS['ewc_meta_reads'] as $read ) { ewc_assert( ! in_array( $read[0], array( 2, 3, 4, 5, 6 ), true ), 'Read excluded post metadata' ); }
} );
ewc_test( 'pagination is deterministic and reports true public totals', function () {
	$snapshot = EWebCity_SEO_Bridge::snapshot( '2', '1' );
	ewc_equal( array( 7 ), array_column( $snapshot['posts'], 'id' ) );
	ewc_equal( array( 'page' => 2, 'per_page' => 1, 'total_posts' => 2, 'total_pages' => 2 ), $snapshot['pagination'] );
} );
ewc_test( 'invalid pagination is rejected before database reads', function () {
	foreach ( array( 0, -1, 101, '1.5', '1e2', '01', '', array( 1 ), true, 1.0, '999999999999999999' ) as $value ) {
		ewc_error( EWebCity_SEO_Bridge::snapshot( $value, 20 ), 'ewebcity_invalid_pagination', 400 );
		ewc_error( EWebCity_SEO_Bridge::snapshot( 1, $value ), 'ewebcity_invalid_pagination', 400 );
	}
	ewc_equal( array(), $GLOBALS['ewc_query_calls'] );
} );
ewc_test( 'empty public collections and out of range pages remain explicit', function () {
	$GLOBALS['ewc_posts'] = array();
	$snapshot = EWebCity_SEO_Bridge::snapshot();
	ewc_equal( 0, $snapshot['pagination']['total_posts'] ); ewc_equal( 0, $snapshot['pagination']['total_pages'] );
	ewc_error( EWebCity_SEO_Bridge::snapshot( 2, 20 ), 'ewebcity_invalid_page', 400 );
	$GLOBALS['ewc_types'] = array();
	$GLOBALS['ewc_query_calls'] = array();
	ewc_error( EWebCity_SEO_Bridge::snapshot( 2, 20 ), 'ewebcity_invalid_page', 400 );
	ewc_equal( array(), $GLOBALS['ewc_query_calls'] );
} );
ewc_test( 'query hooks or races cannot inject private or password protected posts', function () {
	foreach ( array( 2, 3, 4, 5, 6, 999 ) as $id ) {
		$GLOBALS['ewc_query_override'] = array( $id );
		ewc_error( EWebCity_SEO_Bridge::snapshot(), 'ewebcity_public_scope_changed', 409 );
	}
	ewc_equal( array(), $GLOBALS['ewc_meta_reads'] );
} );
ewc_test( 'oversized query result fails closed', function () {
	$GLOBALS['ewc_query_override'] = array( 1, 7 );
	ewc_error( EWebCity_SEO_Bridge::snapshot( 1, 1 ), 'ewebcity_query_changed', 500 );
} );
ewc_test( 'long UTF-8 values truncate at a character boundary with diagnostics', function () {
	$GLOBALS['ewc_meta'][1]['_yoast_wpseo_title'] = str_repeat( 'বাংলা', 1000 );
	$snapshot = EWebCity_SEO_Bridge::snapshot(); $row = $snapshot['posts'][0]; $meta = (array) $row['metadata'];
	ewc_assert( strlen( $meta['yoast']['title'] ) <= 8192, 'Unbounded string' );
	ewc_equal( 1, preg_match( '//u', $meta['yoast']['title'] ) );
	ewc_equal( array( 'yoast.title' ), $row['truncated_fields'] );
} );
ewc_test( 'invalid UTF-8, NUL and non-scalar metadata are omitted visibly', function () {
	$GLOBALS['ewc_meta'][1]['_yoast_wpseo_title'] = "unsafe\0value";
	$GLOBALS['ewc_meta'][1]['_yoast_wpseo_metadesc'] = array( 'unexpected' );
	$GLOBALS['ewc_meta'][1]['rank_math_description'] = "\xff";
	$GLOBALS['ewc_meta'][1]['rank_math_robots'] = array( 'index', "bad\0flag", array( 'nested' ) );
	$row = EWebCity_SEO_Bridge::snapshot()['posts'][0]; $meta = (array) $row['metadata'];
	ewc_equal( null, $meta['yoast']['title'] ); ewc_equal( null, $meta['yoast']['description'] );
	ewc_equal( null, $meta['rankmath']['description'] ); ewc_equal( array( 'index' ), $meta['rankmath']['robots'] );
	foreach ( array( 'yoast.title', 'yoast.description', 'rankmath.description', 'rankmath.robots' ) as $field ) { ewc_assert( in_array( $field, $row['omitted_fields'], true ), 'Missing omission diagnostic' ); }
} );
ewc_test( 'Rank Math robots arrays are bounded without splitting strings into invented flags', function () {
	$GLOBALS['ewc_meta'][1]['rank_math_robots'] = array_fill( 0, 40, 'noindex' );
	$row = EWebCity_SEO_Bridge::snapshot()['posts'][0]; $meta = (array) $row['metadata'];
	ewc_equal( 32, count( $meta['rankmath']['robots'] ) ); ewc_equal( array( 'rankmath.robots' ), $row['truncated_fields'] );
	$GLOBALS['ewc_meta'][1]['rank_math_robots'] = 'noindex,nofollow';
	$row = EWebCity_SEO_Bridge::snapshot()['posts'][0]; $meta = (array) $row['metadata'];
	ewc_equal( array(), $meta['rankmath']['robots'] ); ewc_equal( array( 'rankmath.robots' ), $row['omitted_fields'] );
} );
ewc_test( 'timestamps are UTC and invalid stored timestamps remain null', function () {
	$GLOBALS['ewc_posts'][7]->post_modified_gmt = '0000-00-00 00:00:00';
	$snapshot = EWebCity_SEO_Bridge::snapshot();
	ewc_equal( '2026-11-12T10:20:30Z', $snapshot['posts'][0]['modified_gmt'] ); ewc_equal( null, $snapshot['posts'][1]['modified_gmt'] );
	ewc_equal( 1, preg_match( '/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/D', $snapshot['generated_at'] ) );
} );
ewc_test( 'visibility reflects the stored WordPress discourage setting', function () {
	$GLOBALS['ewc_options']['blog_public'] = '0';
	ewc_equal( 'discourage', EWebCity_SEO_Bridge::snapshot()['site']['search_visibility'] );
} );
ewc_test( 'unsafe site URLs, permalinks and NUL site settings fail closed', function () {
	$GLOBALS['ewc_home'] = 'https://username:password@example.org';
	ewc_error( EWebCity_SEO_Bridge::snapshot(), 'ewebcity_invalid_site', 500 );
	$GLOBALS['ewc_home'] = 'https://example.org'; $GLOBALS['ewc_options']['permalink_structure'] = "/bad\0/%postname%/";
	ewc_error( EWebCity_SEO_Bridge::snapshot(), 'ewebcity_invalid_site', 500 );
	$GLOBALS['ewc_options']['permalink_structure'] = '/%postname%/'; $GLOBALS['ewc_posts'][1]->url = 'javascript:alert(1)';
	ewc_error( EWebCity_SEO_Bridge::snapshot(), 'ewebcity_invalid_permalink', 500 );
} );
ewc_test( 'REST rechecks permission and sets private no-store headers', function () {
	$request = new WP_REST_Request( array( 'page' => 1, 'per_page' => 20 ) );
	$GLOBALS['ewc_capable'] = false; ewc_error( EWebCity_SEO_Bridge::rest_snapshot( $request ), 'ewebcity_forbidden', 403 );
	$GLOBALS['ewc_capable'] = true; $response = EWebCity_SEO_Bridge::rest_snapshot( $request );
	ewc_equal( 200, $response->get_status() ); ewc_equal( 'private, no-store, max-age=0', $response->get_headers()['Cache-Control'] );
} );
ewc_test( 'download rejects unauthorised users, GET, and invalid nonces before querying', function () {
	foreach ( array( 'capability', 'method', 'nonce' ) as $case ) {
		ewc_reset_fixture();
		if ( 'capability' === $case ) { $GLOBALS['ewc_capable'] = false; }
		if ( 'method' === $case ) { $_SERVER['REQUEST_METHOD'] = 'GET'; }
		if ( 'nonce' === $case ) { $GLOBALS['ewc_nonce_valid'] = false; }
		try { EWebCity_SEO_Bridge::download(); throw new RuntimeException( 'Expected refusal' ); }
		catch ( EWebCity_Test_Die $error ) { ewc_equal( 'method' === $case ? 405 : 403, $error->getCode() ); }
		ewc_equal( array(), $GLOBALS['ewc_query_calls'] );
	}
} );
ewc_test( 'Tools screen has protected export and existing edit/provider links', function () {
	EWebCity_SEO_Bridge::admin_menu(); ewc_equal( 'manage_options', $GLOBALS['ewc_menu'][2] );
	ob_start(); EWebCity_SEO_Bridge::admin_page(); $html = ob_get_clean();
	foreach ( array( 'Auditor: Mahim', 'ewebcity_seo_nonce', 'method="post"', 'Edit post and SEO settings', 'wpseo_dashboard', 'page=rank-math' ) as $text ) { ewc_assert( false !== strpos( $html, $text ), 'Missing UI affordance ' . $text ); }
	ewc_assert( false === strpos( $html, 'BODY_MUST_NOT_EXPORT' ), 'Rendered body content' );
} );
ewc_test( 'encoded snapshots over 10 MiB fail as a whole and advise smaller pages', function () {
	$meta = $GLOBALS['ewc_meta'][1]; $meta['rank_math_robots'] = array_fill( 0, 32, str_repeat( 'x', 8192 ) );
	$GLOBALS['ewc_posts'] = array(); $GLOBALS['ewc_meta'] = array();
	for ( $id = 1; $id <= 50; ++$id ) { $GLOBALS['ewc_posts'][ $id ] = new WP_Post( $id ); $GLOBALS['ewc_meta'][ $id ] = $meta; }
	$error = EWebCity_SEO_Bridge::snapshot( 1, 100 );
	ewc_error( $error, 'ewebcity_snapshot_too_large', 413 );
	ewc_assert( false !== strpos( $error->get_error_message(), 'per_page' ), 'No actionable size guidance' );
	ewc_error( EWebCity_SEO_Bridge::rest_snapshot( new WP_REST_Request( array( 'page' => 1, 'per_page' => 100 ) ) ), 'ewebcity_snapshot_too_large', 413 );
} );

echo 'PHP bridge contracts: ' . $passed . ' passed, ' . $failed . " failed. WordPress runtime integration was not exercised.\n";
exit( $failed ? 1 : 0 );
