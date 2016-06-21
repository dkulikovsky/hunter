CREATE TABLE `hunter` (
		  `id` int(10) unsigned NOT NULL auto_increment,
		  `host_id` int(10) unsigned NOT NULL,
		  `key_name` text NOT NULL,
		  `val` text NOT NULL,
		  `updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
		  PRIMARY KEY  (`id`),
		  KEY `host_id` (`host_id`)
) ENGINE=MyISAM AUTO_INCREMENT=1696 DEFAULT CHARSET=utf8;

CREATE TABLE `hosts` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `hostname` varchar(255) NOT NULL DEFAULT '',
  `desc` varchar(255) NOT NULL DEFAULT '',
  PRIMARY KEY (`id`),
  KEY `hostname` (`hostname`)
) ENGINE=MyISAM AUTO_INCREMENT=9808519 DEFAULT CHARSET=utf8
