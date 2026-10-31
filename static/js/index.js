/*
 * ICCP Summer School site: hash router and photo lightbox.
 *
 * URLs look like #page or #page/anchor. Each page is an HTML fragment in
 * pages/<page>.html that is fetched and injected into #content. Fragments are
 * injected with innerHTML, so <script> tags inside them never run: all page
 * behavior lives in this file and is reached through inline onclick handlers
 * or document-level listeners.
 */

var SITE_TITLE = 'ICCP Summer School on Computational Imaging';
var PAGE_TITLES = { courses: 'Courses', photos: 'Photos', sponsors: 'Sponsors' };

var currentPage = null;
var loadToken = 0;

if ('scrollRestoration' in history) {
	history.scrollRestoration = 'manual';
}

function parseHash() {
	var parts = window.location.hash.replace(/^#/, '').split('/');
	return { page: parts[0] || 'home', anchor: decodeURIComponent(parts[1] || '') };
}

function scrollToAnchor(anchor) {
	var target = anchor ? document.getElementById(anchor) : null;
	if (target) {
		target.scrollIntoView();
	}
	return Boolean(target);
}

// Without an anchor, bring the reader back to the navigation bar if they are
// scrolled below it, so a new page starts at its top.
function scrollToContentTop() {
	var nav = document.querySelector('nav');
	if (nav && nav.getBoundingClientRect().top < 0) {
		nav.scrollIntoView();
	}
}

function setActiveButton(page) {
	document.querySelectorAll('nav a.button').forEach(function (button) {
		button.classList.toggle('active-button', button.getAttribute('href') === '#' + page);
	});
}

function showError() {
	document.getElementById('content').innerHTML =
		'<section class="section container is-max-desktop content">' +
		'<p>Sorry, the content could not be loaded.</p></section>';
}

function loadContent() {
	var route = parseHash();
	closePhotoModal();

	if (route.page === currentPage) {
		if (!scrollToAnchor(route.anchor)) {
			scrollToContentTop();
		}
		return;
	}

	var token = ++loadToken;
	var isFirstLoad = currentPage === null;

	if (!/^[a-z]+$/.test(route.page)) {
		currentPage = route.page;
		setActiveButton(null);
		showError();
		return;
	}

	fetch('pages/' + route.page + '.html')
		.then(function (response) {
			if (!response.ok) {
				throw new Error('HTTP error! Status: ' + response.status);
			}
			return response.text();
		})
		.then(function (html) {
			if (token !== loadToken) {
				return; // a newer navigation started while this one was loading
			}
			document.getElementById('content').innerHTML = html;
			currentPage = route.page;
			setActiveButton(route.page);
			document.title = PAGE_TITLES[route.page]
				? PAGE_TITLES[route.page] + ' | ' + SITE_TITLE
				: SITE_TITLE;
			if (!scrollToAnchor(route.anchor) && !isFirstLoad) {
				scrollToContentTop();
			}
		})
		.catch(function (error) {
			if (token !== loadToken) {
				return;
			}
			currentPage = route.page;
			setActiveButton(null);
			showError();
			console.error('Error loading page:', error);
		});
}

/* ------------------------------------------------------------------ */
/* Photo lightbox (markup lives in index.html, items in the pages)     */
/* ------------------------------------------------------------------ */

var currentGalleryIndex = -1;

function getGalleryItems() {
	return Array.from(document.querySelectorAll('#content .gallery-item'));
}

function showPhotoAt(index) {
	var items = getGalleryItems();
	var modal = document.getElementById('photo-modal');
	if (!modal || items.length === 0) {
		return;
	}
	index = ((index % items.length) + items.length) % items.length;
	currentGalleryIndex = index;

	var item = items[index];
	var thumb = item.querySelector('img');
	var img = modal.querySelector('.modal-content img');
	img.removeAttribute('src'); // don't flash the previous photo while the next one loads
	img.alt = thumb ? thumb.alt : '';
	img.src = item.dataset.src;
	modal.querySelector('.photo-modal-text').textContent = item.dataset.caption || '';
	modal.querySelector('.photo-modal-count').textContent = (index + 1) + ' / ' + items.length;
	modal.classList.add('is-active');
	document.documentElement.classList.add('is-clipped');
}

function openPhotoModal(el) {
	showPhotoAt(getGalleryItems().indexOf(el));
}

function navigatePhoto(delta) {
	showPhotoAt(currentGalleryIndex + delta);
}

function closePhotoModal() {
	var modal = document.getElementById('photo-modal');
	if (modal) {
		modal.classList.remove('is-active');
	}
	document.documentElement.classList.remove('is-clipped');
}

document.addEventListener('keydown', function (event) {
	var modal = document.getElementById('photo-modal');
	if (modal && modal.classList.contains('is-active')) {
		if (event.key === 'Escape') {
			closePhotoModal();
		} else if (event.key === 'ArrowLeft') {
			navigatePhoto(-1);
		} else if (event.key === 'ArrowRight') {
			navigatePhoto(1);
		}
		return;
	}
	// Gallery tiles are focusable (tabindex="0"); Enter opens them.
	if (event.key === 'Enter' && event.target.classList && event.target.classList.contains('gallery-item')) {
		openPhotoModal(event.target);
	}
});

window.addEventListener('hashchange', loadContent);
loadContent();
