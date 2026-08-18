<?php
/**
 * Plugin Name: error.wtf Radio Player Embed
 * Description: Embed the WEB CASU radio player as a responsive iframe on the
 *              "RADIO PLAYLIST" page (id 50548), directly below the existing
 *              Webamp embed. The player is lifted above the page's decorative
 *              particle/rain canvas so clicks and audio controls reach it.
 *              Only affects that one page; fully reversible by removing this
 *              file.
 */
if (!defined('ABSPATH')) {
    exit;
}

add_action('wp_head', function () {
    // Only on this page: the decorative full-page overlays (particles rain +
    // matrix exit gate) must never swallow clicks, otherwise the embedded
    // player could not be operated (play/pause/station selection).
    if (!is_page('radio-playlist')) {
        return;
    }
    echo '<style id="error-wtf-radio-player-css">'
        . '#error-particles-stage,.error-particles-stage,.error-particles-stage canvas,'
        . '.particles-js-canvas-el,'
        . '.error-exit-gate,.error-exit-gate__background,.error-exit-gate *{pointer-events:none!important}'
        . '</style>';
});

add_filter('the_content', function ($content) {
    if (!is_page('radio-playlist')) {
        return $content;
    }
    $player = '<div style="position:relative;width:100%;max-width:100%;margin:0 0 12px;overflow:hidden;z-index:10;">'
        . '<iframe style="display:block;width:100%!important;height:clamp(440px, 70vh, 620px)!important;'
        . 'min-height:440px!important;max-height:620px!important;border:0;margin:0;" '
        . 'title="WEB CASU Radio Player" '
        . 'src="https://error.wtf/web-casu/?embed=1&v=6" '
        . 'allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe></div>';
    return $content . $player;
});
