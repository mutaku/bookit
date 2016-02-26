$(document).tooltip({
	items: "a[title]"
});
$(document).ready(function() {
	$('#messages').dialog({
		autoOpen: true,
		width: 500,
		height: 200,
		modal: true
	});
	$('.slider').click(function() {
		$(this).parent().slideToggle();
	});
	$('.message-obj').click(function() {
		var loc = $(this).attr('id')
		window.location.href = "/scheduling/messages/#" + loc
	});
});