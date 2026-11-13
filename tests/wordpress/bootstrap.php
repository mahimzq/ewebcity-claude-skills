<?php
/** Minimal WordPress API doubles. These tests do not boot WordPress or a database. */
define( 'ABSPATH', __DIR__ . '/' );

class WP_Error {
	private $code;
	private $message;
	private $data;
	public function __construct( $code, $message, $data = array() ) { $this->code = $code; $this->message = $message; $this->data = $data; }
	public function get_error_code() { return $this->code; }
	public function get_error_message() { return $this->message; }
	public function get_error_data() { return $this->data; }
}
class WP_REST_Server { const READABLE = 'GET'; }
class WP_REST_Request {
	private $params;
	public function __construct( $params ) { $this->params = $params; }
	public function get_param( $name ) { return isset( $this->params[ $name ] ) ? $this->params[ $name ] : null; }
}
class WP_REST_Response {
	private $data;
	private $status;
	private $headers = array();
	public function __construct( $data, $status ) { $this->data = $data; $this->status = $status; }
	public function header( $key, $value ) { $this->headers[ $key ] = $value; }
	public function get_data() { return $this->data; }
	public function get_status() { return $this->status; }
	public function get_headers() { return $this->headers; }
}
class WP_Post {
	public $ID;
	public $post_type = 'post';
	public $post_status = 'publish';
	public $post_password = '';
	public $post_modified_gmt = '2026-11-12 10:20:30';
	public $post_content = 'BODY_MUST_NOT_EXPORT';
	public $post_excerpt = 'EXCERPT_MUST_NOT_EXPORT';
	public $post_author = 9123;
	public $url;
	public function __construct( $id, $values = array() ) {
		$this->ID = $id;
		$this->url = 'https://example.org/post-' . $id . '/';
		foreach ( $values as $key => $value ) { $this->$key = $value; }
	}
}
class WP_Query {
	public $posts = array();
	public $found_posts = 0;
	public function __construct( $args ) {
		$GLOBALS['ewc_query_calls'][] = $args;
		if ( null !== $GLOBALS['ewc_query_override'] ) {
			$this->posts = $GLOBALS['ewc_query_override'];
			$this->found_posts = count( $this->posts );
			return;
		}
		$eligible = array();
		foreach ( $GLOBALS['ewc_posts'] as $post ) {
			if ( in_array( $post->post_type, $args['post_type'], true ) && $post->post_status === $args['post_status']
				&& ( ! isset( $args['has_password'] ) || (bool) $args['has_password'] === ( '' !== $post->post_password ) ) ) {
				$eligible[] = $post->ID;
			}
		}
		sort( $eligible, SORT_NUMERIC );
		$this->found_posts = count( $eligible );
		$this->posts = array_slice( $eligible, ( $args['paged'] - 1 ) * $args['posts_per_page'], $args['posts_per_page'] );
	}
}
class EWebCity_Test_Die extends RuntimeException {}

$GLOBALS['ewc_actions'] = array();
function add_action( $hook, $callback ) { $GLOBALS['ewc_actions'][ $hook ] = $callback; }
function current_user_can( $capability ) { return 'manage_options' === $capability && $GLOBALS['ewc_capable']; }
function is_wp_error( $value ) { return $value instanceof WP_Error; }
function register_rest_route( $namespace, $route, $definition ) { $GLOBALS['ewc_route'] = array( $namespace, $route, $definition ); }
function add_management_page( $title, $menu, $capability, $slug, $callback ) { $GLOBALS['ewc_menu'] = array( $title, $menu, $capability, $slug, $callback ); }
function home_url( $path = '' ) { return $GLOBALS['ewc_home'] . $path; }
function site_url( $path = '' ) { return 'https://example.org/wordpress' . $path; }
function admin_url( $path = '' ) { return 'https://example.org/wordpress/wp-admin/' . $path; }
function rest_url( $path = '' ) { return 'https://example.org/wp-json/' . $path; }
function wp_parse_url( $value ) { return parse_url( $value ); }
function get_option( $name, $default = false ) {
	$GLOBALS['ewc_option_reads'][] = $name;
	return array_key_exists( $name, $GLOBALS['ewc_options'] ) ? $GLOBALS['ewc_options'][ $name ] : $default;
}
function get_post_types( $args, $output, $operator ) {
	$types = array();
	foreach ( $GLOBALS['ewc_types'] as $name => $definition ) {
		if ( $definition->public === $args['public'] && $definition->publicly_queryable === $args['publicly_queryable'] ) { $types[ $name ] = $name; }
	}
	return $types;
}
function get_post_type_object( $type ) { return isset( $GLOBALS['ewc_types'][ $type ] ) ? $GLOBALS['ewc_types'][ $type ] : null; }
function get_post( $id ) { return isset( $GLOBALS['ewc_posts'][ $id ] ) ? $GLOBALS['ewc_posts'][ $id ] : null; }
function get_permalink( $id ) { return $GLOBALS['ewc_posts'][ $id ]->url; }
function get_edit_post_link( $id, $context ) { return admin_url( 'post.php?post=' . $id . '&action=edit' ); }
function metadata_exists( $type, $id, $key ) { return isset( $GLOBALS['ewc_meta'][ $id ] ) && array_key_exists( $key, $GLOBALS['ewc_meta'][ $id ] ); }
function get_post_meta( $id, $key, $single ) {
	$GLOBALS['ewc_meta_reads'][] = array( $id, $key );
	return metadata_exists( 'post', $id, $key ) ? $GLOBALS['ewc_meta'][ $id ][ $key ] : '';
}
function wp_json_encode( $value, $flags = 0 ) { return json_encode( $value, $flags ); }
function wp_unslash( $value ) { return $value; }
function esc_html( $value ) { return htmlspecialchars( (string) $value, ENT_QUOTES, 'UTF-8' ); }
function esc_url( $value ) { return preg_match( '/^(?:javascript|data|vbscript):/i', $value ) ? '' : esc_html( $value ); }
function wp_nonce_field( $action, $name ) { echo '<input type="hidden" name="' . esc_html( $name ) . '" value="fixture-nonce">'; }
function check_admin_referer( $action, $name ) {
	$GLOBALS['ewc_nonce_checks'][] = array( $action, $name );
	if ( ! $GLOBALS['ewc_nonce_valid'] ) { wp_die( 'Invalid nonce', 'Forbidden', array( 'response' => 403 ) ); }
}
function wp_die( $message, $title = '', $args = array() ) { throw new EWebCity_Test_Die( $message, isset( $args['response'] ) ? $args['response'] : 500 ); }
function nocache_headers() {}
function submit_button( $text, $type ) { echo '<button type="submit">' . esc_html( $text ) . '</button>'; }
function update_post_meta() { throw new RuntimeException( 'Metadata mutation attempted' ); }
function update_option() { throw new RuntimeException( 'Option mutation attempted' ); }
function wp_update_post() { throw new RuntimeException( 'Post mutation attempted' ); }
function wp_remote_get() { throw new RuntimeException( 'Unexpected outbound request' ); }

function ewc_reset_fixture() {
	$GLOBALS['ewc_capable'] = true;
	$GLOBALS['ewc_nonce_valid'] = true;
	$GLOBALS['ewc_nonce_checks'] = array();
	$GLOBALS['ewc_query_calls'] = array();
	$GLOBALS['ewc_query_override'] = null;
	$GLOBALS['ewc_meta_reads'] = array();
	$GLOBALS['ewc_option_reads'] = array();
	$GLOBALS['ewc_home'] = 'https://example.org';
	$GLOBALS['ewc_options'] = array( 'blog_public' => '1', 'permalink_structure' => '/%postname%/', 'secret_api_key' => 'KEY_MUST_NOT_EXPORT' );
	$GLOBALS['ewc_types'] = array(
		'post' => (object) array( 'public' => true, 'publicly_queryable' => true ),
		'page' => (object) array( 'public' => true, 'publicly_queryable' => true ),
		'secret' => (object) array( 'public' => false, 'publicly_queryable' => false ),
		'hidden' => (object) array( 'public' => true, 'publicly_queryable' => false ),
	);
	$GLOBALS['ewc_posts'] = array(
		1 => new WP_Post( 1 ),
		2 => new WP_Post( 2, array( 'post_password' => 'PASSWORD_MUST_NOT_EXPORT' ) ),
		3 => new WP_Post( 3, array( 'post_status' => 'private' ) ),
		4 => new WP_Post( 4, array( 'post_status' => 'draft' ) ),
		5 => new WP_Post( 5, array( 'post_type' => 'secret' ) ),
		6 => new WP_Post( 6, array( 'post_type' => 'hidden' ) ),
		7 => new WP_Post( 7, array( 'post_type' => 'page' ) ),
	);
	$GLOBALS['ewc_meta'] = array( 1 => array(
		'_yoast_wpseo_title' => '%%title%% | Example', '_yoast_wpseo_metadesc' => '',
		'_yoast_wpseo_meta-robots-noindex' => '2', '_yoast_wpseo_meta-robots-nofollow' => '0',
		'_yoast_wpseo_meta-robots-adv' => 'nosnippet',
		'rank_math_title' => '%title% | Example', 'rank_math_description' => 'Stored description',
		'rank_math_canonical_url' => '/raw-relative-canonical', 'rank_math_robots' => array( 'index', 'follow' ),
		'private_key' => 'META_KEY_MUST_NOT_EXPORT',
	) );
	$_SERVER['REQUEST_METHOD'] = 'POST';
	$_POST = array();
}

ewc_reset_fixture();
require dirname( __DIR__, 2 ) . '/integrations/wordpress/ewebcity-seo-bridge/ewebcity-seo-bridge.php';
