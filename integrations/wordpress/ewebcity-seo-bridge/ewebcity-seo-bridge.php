<?php
/**
 * Plugin Name: eWebCity SEO Bridge
 * Description: Administrator-only, read-only snapshots of public WordPress SEO overrides for eWebCity audits.
 * Version: 2.2.0
 * Requires at least: 5.6
 * Requires PHP: 7.4
 * Author: eWebCity
 * License: MIT
 * License URI: https://opensource.org/license/mit/
 * Text Domain: ewebcity-seo-bridge
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class EWebCity_SEO_Bridge {
	const VERSION = '2.2.0';
	const MAX_PAGE = 100;
	const MAX_PER_PAGE = 100;
	const MAX_TEXT_BYTES = 8192;
	const MAX_ROBOTS = 32;
	const MAX_SNAPSHOT_BYTES = 10485760;
	const SEMANTICS = 'stored_provider_overrides_not_rendered_metadata';

	public static function boot() {
		add_action( 'admin_menu', array( __CLASS__, 'admin_menu' ) );
		add_action( 'admin_post_ewebcity_seo_download', array( __CLASS__, 'download' ) );
		add_action( 'rest_api_init', array( __CLASS__, 'register_rest' ) );
	}

	public static function can_read() {
		return current_user_can( 'manage_options' );
	}

	public static function providers() {
		$providers = array();
		foreach ( array( 'yoast' => 'WPSEO_VERSION', 'rankmath' => 'RANK_MATH_VERSION' ) as $id => $constant ) {
			if ( defined( $constant ) ) {
				$value = constant( $constant );
				$version = is_string( $value ) || is_numeric( $value ) ? (string) $value : '';
				// Plugin versions are identifiers, never an inventory of other settings.
				$version = preg_replace( '/[^A-Za-z0-9._+\-]/', '', $version );
				$providers[] = array( 'id' => $id, 'active' => true, 'version' => substr( $version, 0, 80 ) );
			}
		}
		return $providers;
	}

	public static function valid_page_argument( $value, $request = null, $parameter = '' ) {
		return self::bounded_integer( $value, self::MAX_PAGE ) !== false;
	}

	public static function valid_per_page_argument( $value, $request = null, $parameter = '' ) {
		return self::bounded_integer( $value, self::MAX_PER_PAGE ) !== false;
	}

	private static function bounded_integer( $value, $maximum ) {
		if ( ! is_int( $value ) && ! is_string( $value ) ) {
			return false;
		}
		$value = (string) $value;
		if ( ! preg_match( '/^[1-9][0-9]{0,2}$/D', $value ) ) {
			return false;
		}
		$number = (int) $value;
		return $number <= $maximum ? $number : false;
	}

	public static function register_rest() {
		register_rest_route( 'ewebcity/v1', '/snapshot', array(
			'methods' => WP_REST_Server::READABLE,
			'permission_callback' => array( __CLASS__, 'can_read' ),
			'callback' => array( __CLASS__, 'rest_snapshot' ),
			'args' => array(
				'page' => array( 'default' => 1, 'validate_callback' => array( __CLASS__, 'valid_page_argument' ) ),
				'per_page' => array( 'default' => 20, 'validate_callback' => array( __CLASS__, 'valid_per_page_argument' ) ),
			),
		) );
	}

	public static function rest_snapshot( $request ) {
		// Recheck inside the shared builder as well as in permission_callback.
		$snapshot = self::snapshot( $request->get_param( 'page' ), $request->get_param( 'per_page' ) );
		if ( is_wp_error( $snapshot ) ) {
			return $snapshot;
		}
		$response = new WP_REST_Response( $snapshot, 200 );
		$response->header( 'Cache-Control', 'private, no-store, max-age=0' );
		$response->header( 'Pragma', 'no-cache' );
		$response->header( 'X-Content-Type-Options', 'nosniff' );
		return $response;
	}

	private static function valid_url( $value ) {
		if ( ! is_string( $value ) || strlen( $value ) > self::MAX_TEXT_BYTES || preg_match( '/[\x00-\x20\x7f]/', $value )
			|| 1 !== preg_match( '//u', $value ) ) {
			return false;
		}
		$parts = wp_parse_url( $value );
		return is_array( $parts ) && ! empty( $parts['host'] ) && isset( $parts['scheme'] )
			&& in_array( strtolower( $parts['scheme'] ), array( 'http', 'https' ), true )
			&& ! isset( $parts['user'] ) && ! isset( $parts['pass'] );
	}

	private static function text_value( $value, $field, &$truncated, &$omitted ) {
		if ( ! is_string( $value ) && ! is_int( $value ) && ! is_float( $value ) ) {
			$omitted[] = $field;
			return null;
		}
		$value = (string) $value;
		if ( false !== strpos( $value, "\0" ) || 1 !== preg_match( '//u', $value ) ) {
			$omitted[] = $field;
			return null;
		}
		if ( strlen( $value ) > self::MAX_TEXT_BYTES ) {
			$value = substr( $value, 0, self::MAX_TEXT_BYTES );
			// The original was valid UTF-8; remove at most the incomplete final code point.
			while ( '' !== $value && 1 !== preg_match( '//u', $value ) ) {
				$value = substr( $value, 0, -1 );
			}
			$truncated[] = $field;
		}
		return $value;
	}

	private static function stored_text( $post_id, $key, $field, &$truncated, &$omitted ) {
		if ( ! metadata_exists( 'post', $post_id, $key ) ) {
			return null;
		}
		return self::text_value( get_post_meta( $post_id, $key, true ), $field, $truncated, $omitted );
	}

	private static function stored_robots( $post_id, &$truncated, &$omitted ) {
		if ( ! metadata_exists( 'post', $post_id, 'rank_math_robots' ) ) {
			return array();
		}
		$value = get_post_meta( $post_id, 'rank_math_robots', true );
		if ( ! is_array( $value ) ) {
			$omitted[] = 'rankmath.robots';
			return array();
		}
		if ( count( $value ) > self::MAX_ROBOTS ) {
			$truncated[] = 'rankmath.robots';
		}
		$robots = array();
		foreach ( array_slice( array_values( $value ), 0, self::MAX_ROBOTS ) as $item ) {
			// Rank Math stores an array of flags; do not stringify objects or nested arrays.
			if ( ! is_string( $item ) ) {
				$omitted[] = 'rankmath.robots';
				continue;
			}
			$text = self::text_value( $item, 'rankmath.robots', $truncated, $omitted );
			if ( null !== $text ) {
				$robots[] = $text;
			}
		}
		return $robots;
	}

	private static function modified_gmt( $value ) {
		if ( ! is_string( $value ) || ! preg_match( '/^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$/D', $value ) ) {
			return null;
		}
		$date = DateTimeImmutable::createFromFormat( '!Y-m-d H:i:s', $value, new DateTimeZone( 'UTC' ) );
		if ( false === $date || $date->format( 'Y-m-d H:i:s' ) !== $value || '0000' === substr( $value, 0, 4 ) ) {
			return null;
		}
		return $date->format( 'Y-m-d\TH:i:s\Z' );
	}

	private static function finish_snapshot( $snapshot ) {
		if ( $snapshot['pagination']['page'] > max( 1, $snapshot['pagination']['total_pages'] ) ) {
			return new WP_Error( 'ewebcity_invalid_page', 'The requested page exceeds the eligible public-post count. Start with page 1.', array( 'status' => 400 ) );
		}
		// Default JSON escaping bounds REST output even when non-ASCII characters
		// or control characters take more bytes than their stored UTF-8 values.
		$json = wp_json_encode( $snapshot );
		if ( false === $json ) {
			return new WP_Error( 'ewebcity_json_failed', 'The snapshot could not be encoded as JSON.', array( 'status' => 500 ) );
		}
		if ( strlen( $json ) > self::MAX_SNAPSHOT_BYTES ) {
			return self::size_error();
		}
		return $snapshot;
	}

	private static function size_error() {
		return new WP_Error( 'ewebcity_snapshot_too_large', 'The snapshot exceeds 10 MiB. Reduce per_page and retry.', array( 'status' => 413 ) );
	}

	public static function snapshot( $page = 1, $per_page = 20 ) {
		if ( ! self::can_read() ) {
			return new WP_Error( 'ewebcity_forbidden', 'Administrator capability manage_options is required.', array( 'status' => 403 ) );
		}
		$page = self::bounded_integer( $page, self::MAX_PAGE );
		$per_page = self::bounded_integer( $per_page, self::MAX_PER_PAGE );
		if ( false === $page || false === $per_page ) {
			return new WP_Error( 'ewebcity_invalid_pagination', 'page and per_page must be integers from 1 to 100.', array( 'status' => 400 ) );
		}
		$home = home_url( '/' );
		$site = site_url( '/' );
		$structure = get_option( 'permalink_structure', '' );
		if ( ! self::valid_url( $home ) || ! self::valid_url( $site ) || ! is_string( $structure )
			|| strlen( $structure ) > self::MAX_TEXT_BYTES || false !== strpos( $structure, "\0" ) || 1 !== preg_match( '//u', $structure ) ) {
			return new WP_Error( 'ewebcity_invalid_site', 'The site URL or permalink configuration cannot be represented safely.', array( 'status' => 500 ) );
		}
		$providers = self::providers();
		$snapshot = array(
			'format' => 'ewebcity-wordpress-snapshot',
			'schema_version' => '1.0',
			'bridge_version' => self::VERSION,
			'generated_at' => gmdate( 'Y-m-d\TH:i:s\Z' ),
			'auditor' => 'Mahim',
			'metadata_semantics' => self::SEMANTICS,
			'site' => array( 'home_url' => $home, 'site_url' => $site,
				'search_visibility' => '0' === (string) get_option( 'blog_public', '1' ) ? 'discourage' : 'allow',
				'permalink_structure' => $structure ),
			'providers' => $providers,
			'pagination' => array( 'page' => $page, 'per_page' => $per_page, 'total_posts' => 0, 'total_pages' => 0 ),
			'posts' => array(),
		);
		$types = array_values( get_post_types( array( 'public' => true, 'publicly_queryable' => true ), 'names', 'and' ) );
		if ( ! $types ) {
			return self::finish_snapshot( $snapshot );
		}
		$query = new WP_Query( array(
			'post_type' => $types,
			'post_status' => 'publish',
			'has_password' => false,
			'fields' => 'ids',
			'posts_per_page' => $per_page,
			'paged' => $page,
			'orderby' => 'ID',
			'order' => 'ASC',
			'ignore_sticky_posts' => true,
			'no_found_rows' => false,
			'update_post_meta_cache' => false,
			'update_post_term_cache' => false,
			'suppress_filters' => true,
		) );
		if ( count( $query->posts ) > $per_page ) {
			return new WP_Error( 'ewebcity_query_changed', 'The public-post query exceeded its requested bound. No snapshot was exported.', array( 'status' => 500 ) );
		}
		$snapshot['pagination']['total_posts'] = max( 0, (int) $query->found_posts );
		$snapshot['pagination']['total_pages'] = (int) ceil( $snapshot['pagination']['total_posts'] / $per_page );
		$encoded_bytes = strlen( wp_json_encode( $snapshot ) );
		foreach ( $query->posts as $post_id ) {
			$post = get_post( $post_id );
			$type = $post instanceof WP_Post ? get_post_type_object( $post->post_type ) : null;
			// Recheck after querying: never export a newly private/password-protected post
			// or a result injected by another plugin's query hooks.
			if ( ! ( $post instanceof WP_Post ) || 'publish' !== $post->post_status || '' !== $post->post_password
				|| ! in_array( $post->post_type, $types, true ) || ! $type || ! $type->public || ! $type->publicly_queryable ) {
				return new WP_Error( 'ewebcity_public_scope_changed', 'Public-post eligibility changed during collection. Retry the snapshot.', array( 'status' => 409 ) );
			}
			$url = get_permalink( $post->ID );
			if ( ! self::valid_url( $url ) ) {
				return new WP_Error( 'ewebcity_invalid_permalink', 'A public permalink cannot be represented safely. No snapshot was exported.', array( 'status' => 500 ) );
			}
			$metadata = array();
			$truncated = array();
			$omitted = array();
			foreach ( $providers as $provider ) {
				if ( 'yoast' === $provider['id'] ) {
					$keys = array( 'title' => '_yoast_wpseo_title', 'description' => '_yoast_wpseo_metadesc',
						'canonical' => '_yoast_wpseo_canonical', 'robots_noindex' => '_yoast_wpseo_meta-robots-noindex',
						'robots_nofollow' => '_yoast_wpseo_meta-robots-nofollow', 'robots_advanced' => '_yoast_wpseo_meta-robots-adv' );
					foreach ( $keys as $field => $key ) {
						$metadata['yoast'][ $field ] = self::stored_text( $post->ID, $key, 'yoast.' . $field, $truncated, $omitted );
					}
				} elseif ( 'rankmath' === $provider['id'] ) {
					foreach ( array( 'title' => 'rank_math_title', 'description' => 'rank_math_description', 'canonical' => 'rank_math_canonical_url' ) as $field => $key ) {
						$metadata['rankmath'][ $field ] = self::stored_text( $post->ID, $key, 'rankmath.' . $field, $truncated, $omitted );
					}
					$metadata['rankmath']['robots'] = self::stored_robots( $post->ID, $truncated, $omitted );
				}
			}
			$row = array( 'id' => (int) $post->ID, 'type' => $post->post_type, 'url' => $url,
				'modified_gmt' => self::modified_gmt( $post->post_modified_gmt ),
				'metadata' => (object) $metadata, 'truncated_fields' => array_values( array_unique( $truncated ) ),
				'omitted_fields' => array_values( array_unique( $omitted ) ) );
			$encoded_row = wp_json_encode( $row );
			if ( false === $encoded_row ) {
				return new WP_Error( 'ewebcity_json_failed', 'The snapshot could not be encoded as JSON.', array( 'status' => 500 ) );
			}
			$encoded_bytes += strlen( $encoded_row ) + 1;
			if ( $encoded_bytes > self::MAX_SNAPSHOT_BYTES ) {
				return self::size_error();
			}
			$snapshot['posts'][] = $row;
		}
		return self::finish_snapshot( $snapshot );
	}

	public static function admin_menu() {
		add_management_page( 'eWebCity SEO Bridge', 'eWebCity SEO', 'manage_options', 'ewebcity-seo', array( __CLASS__, 'admin_page' ) );
	}

	public static function download() {
		if ( ! self::can_read() ) {
			wp_die( 'Administrator capability manage_options is required.', 'Forbidden', array( 'response' => 403 ) );
		}
		if ( ! isset( $_SERVER['REQUEST_METHOD'] ) || 'POST' !== $_SERVER['REQUEST_METHOD'] ) {
			wp_die( 'Use the snapshot download form.', 'Method not allowed', array( 'response' => 405 ) );
		}
		check_admin_referer( 'ewebcity_seo_snapshot', 'ewebcity_seo_nonce' );
		$page = isset( $_POST['page'] ) ? wp_unslash( $_POST['page'] ) : 1;
		$per_page = isset( $_POST['per_page'] ) ? wp_unslash( $_POST['per_page'] ) : 20;
		$snapshot = self::snapshot( $page, $per_page );
		if ( is_wp_error( $snapshot ) ) {
			$data = $snapshot->get_error_data();
			wp_die( esc_html( $snapshot->get_error_message() ), 'Snapshot unavailable', array( 'response' => isset( $data['status'] ) ? $data['status'] : 500 ) );
		}
		$json = wp_json_encode( $snapshot, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE );
		if ( false === $json ) {
			wp_die( 'The snapshot could not be encoded as JSON.', 'Snapshot unavailable', array( 'response' => 500 ) );
		}
		if ( strlen( $json ) > self::MAX_SNAPSHOT_BYTES ) {
			wp_die( 'The formatted snapshot exceeds 10 MiB. Reduce per_page and retry.', 'Snapshot too large', array( 'response' => 413 ) );
		}
		nocache_headers();
		header( 'Content-Type: application/json; charset=utf-8' );
		header( 'X-Content-Type-Options: nosniff' );
		header( 'Content-Disposition: attachment; filename="ewebcity-wordpress-snapshot-' . gmdate( 'Ymd-His' ) . '.json"' );
		echo $json; // JSON attachment; never interpolated into an HTML/script context.
		exit;
	}

	public static function admin_page() {
		if ( ! self::can_read() ) {
			wp_die( 'Administrator capability manage_options is required.', 'Forbidden', array( 'response' => 403 ) );
		}
		$providers = self::providers();
		$preview = self::snapshot( 1, 20 );
		?>
		<div class="wrap">
			<h1>eWebCity SEO Bridge</h1>
			<p><strong>Auditor: Mahim</strong> &middot; Read-only SEO evidence &middot; Version <?php echo esc_html( self::VERSION ); ?></p>
			<div class="notice notice-info inline"><p>This snapshot contains stored Yoast / Rank Math overrides for published, public, non-password-protected posts. Empty values and template variables are not final page metadata. Check the actual page response and rendered output before making SEO decisions. The auditor label identifies the report owner; it is not a certification.</p></div>
			<h2>Active SEO providers</h2>
			<?php if ( ! $providers ) : ?>
				<p>Neither Yoast SEO nor Rank Math was detected as active. Public URLs and the selected WordPress visibility settings remain available; provider metadata will be empty.</p>
			<?php else : ?>
				<ul>
				<?php foreach ( $providers as $provider ) : ?>
					<li><strong><?php echo esc_html( 'yoast' === $provider['id'] ? 'Yoast SEO' : 'Rank Math' ); ?></strong>
						<?php echo esc_html( $provider['version'] ); ?> &mdash;
						<a href="<?php echo esc_url( admin_url( 'admin.php?page=' . ( 'yoast' === $provider['id'] ? 'wpseo_dashboard' : 'rank-math' ) ) ); ?>">Open existing plugin controls</a></li>
				<?php endforeach; ?>
				</ul>
			<?php endif; ?>
			<?php if ( count( $providers ) > 1 ) : ?>
				<p>Both providers are active. Their stored overrides are reported separately; inspect the generated page head to determine the effective output.</p>
			<?php endif; ?>
			<h2>Download a snapshot</h2>
			<p>One page per download. Page and page size are limited to 1&ndash;100. The export contains no post body, excerpts, author records, passwords or unrelated plugin options.</p>
			<form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>">
				<input type="hidden" name="action" value="ewebcity_seo_download">
				<?php wp_nonce_field( 'ewebcity_seo_snapshot', 'ewebcity_seo_nonce' ); ?>
				<p><label for="ewebcity-page">Page</label> <input id="ewebcity-page" name="page" type="number" min="1" max="100" value="1" required>
					<label for="ewebcity-per-page">Posts per page</label> <input id="ewebcity-per-page" name="per_page" type="number" min="1" max="100" value="20" required></p>
				<?php submit_button( 'Download JSON snapshot', 'primary' ); ?>
			</form>
			<h2>Public post preview</h2>
			<?php if ( is_wp_error( $preview ) ) : ?>
				<p><?php echo esc_html( $preview->get_error_message() ); ?></p>
			<?php else : ?>
				<p><?php echo esc_html( (string) $preview['pagination']['total_posts'] ); ?> eligible posts; showing the first <?php echo esc_html( (string) count( $preview['posts'] ) ); ?>.</p>
				<table class="widefat striped"><thead><tr><th scope="col">Public URL</th><th scope="col">Type / ID</th><th scope="col">Existing editor</th></tr></thead><tbody>
				<?php foreach ( $preview['posts'] as $post ) : $edit = get_edit_post_link( $post['id'], 'raw' ); ?>
					<tr><td><a href="<?php echo esc_url( $post['url'] ); ?>"><?php echo esc_html( $post['url'] ); ?></a></td>
						<td><?php echo esc_html( $post['type'] . ' / ' . $post['id'] ); ?></td>
						<td><?php if ( $edit ) : ?><a href="<?php echo esc_url( $edit ); ?>">Edit post and SEO settings</a><?php else : ?>No editor access<?php endif; ?></td></tr>
				<?php endforeach; ?>
				<?php if ( ! $preview['posts'] ) : ?><tr><td colspan="3">No eligible public posts were found.</td></tr><?php endif; ?>
				</tbody></table>
			<?php endif; ?>
			<h2>Authenticated automation</h2>
			<p><code><?php echo esc_html( rest_url( 'ewebcity/v1/snapshot' ) ); ?></code></p>
			<p>The GET endpoint requires WordPress authentication and <code>manage_options</code>. Cookie authentication also requires a WordPress REST nonce; use the download form for a browser export. For remote clients, use WordPress Application Passwords over HTTPS and keep credentials outside reports.</p>
		</div>
		<?php
	}
}

EWebCity_SEO_Bridge::boot();
