# Generated by Django 4.2.5 on 2023-10-03 11:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shipping', '0005_auto_20170303_0041'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shippingmethodcountry',
            name='country_code',
            field=models.CharField(blank=True, choices=[('', 'Rest of World'), ('AF', 'Afghanistan'), ('EG', 'Ägypten'), ('AX', 'Åland-Inseln'), ('AL', 'Albanien'), ('DZ', 'Algerien'), ('AS', 'Amerikanisch-Samoa'), ('VI', 'Amerikanische Jungferninseln'), ('AD', 'Andorra'), ('AO', 'Angola'), ('AI', 'Anguilla'), ('AQ', 'Antarktis'), ('AG', 'Antigua und Barbuda'), ('GQ', 'Äquatorialguinea'), ('AR', 'Argentinien'), ('AM', 'Armenien'), ('AW', 'Aruba'), ('AZ', 'Aserbaidschan'), ('ET', 'Äthiopien'), ('AU', 'Australien'), ('BS', 'Bahamas'), ('BH', 'Bahrain'), ('BD', 'Bangladesch'), ('BB', 'Barbados'), ('BE', 'Belgien'), ('BZ', 'Belize'), ('BJ', 'Benin'), ('BM', 'Bermuda'), ('BT', 'Bhutan'), ('BO', 'Bolivien'), ('BQ', 'Bonaire, Sint Eustatius und Saba'), ('BA', 'Bosnien und Herzegowina'), ('BW', 'Botswana'), ('BV', 'Bouvetinsel'), ('BR', 'Brasilien'), ('VG', 'Britische Jungferninseln'), ('IO', 'Britisches Territorium im Indischen Ozean'), ('BN', 'Brunei'), ('BG', 'Bulgarien'), ('BF', 'Burkina Faso'), ('BI', 'Burundi'), ('CL', 'Chile'), ('CN', 'China'), ('MP', 'Commonwealth der Nördlichen Marianen'), ('CK', 'Cookinseln'), ('CR', 'Costa Rica'), ('CI', "Côte d'Ivoire"), ('CW', 'Curaçao'), ('DK', 'Dänemark'), ('DE', 'Deutschland'), ('DM', 'Dominica'), ('DO', 'Dominikanische Republik'), ('DJ', 'Dschibuti'), ('EC', 'Ecuador'), ('SV', 'El Salvador'), ('ER', 'Eritrea'), ('EE', 'Estland'), ('FK', 'Falklandinseln (Malwinen)'), ('FO', 'Faröerinseln'), ('FJ', 'Fidschi'), ('FI', 'Finnland'), ('FR', 'Frankreich'), ('GF', 'Französisch Guinea'), ('PF', 'Französisch-Polynesien'), ('TF', 'Französische Süd- und Antarktisgebiete'), ('GA', 'Gabun'), ('GM', 'Gambia'), ('GE', 'Georgien'), ('GH', 'Ghana'), ('GI', 'Gibraltar'), ('GD', 'Granada'), ('GR', 'Griechenland'), ('GL', 'Grönland'), ('GP', 'Guadeloupe'), ('GU', 'Guam'), ('GT', 'Guatemala'), ('GG', 'Guernsey'), ('GN', 'Guinea'), ('GW', 'Guinea-Bissau'), ('GY', 'Guyana'), ('HT', 'Haiti'), ('HM', 'Heard und McDonaldinseln'), ('HN', 'Honduras'), ('HK', 'Hong Kong'), ('IN', 'Indien'), ('ID', 'Indonesien'), ('IQ', 'Irak'), ('IR', 'Iran'), ('IE', 'Irland'), ('IS', 'Island'), ('IM', 'Isle of Man'), ('IL', 'Israel'), ('IT', 'Italien'), ('JM', 'Jamaika'), ('JP', 'Japan'), ('YE', 'Jemen'), ('JE', 'Jersey'), ('JO', 'Jordanien'), ('KY', 'Kaimaninseln'), ('KH', 'Kambodscha'), ('CM', 'Kamerun'), ('CA', 'Kanada'), ('CV', 'Kap Verde'), ('KZ', 'Kasachstan'), ('QA', 'Katar'), ('KE', 'Kenia'), ('KG', 'Kirgisistan'), ('KI', 'Kirivati'), ('CC', 'Kokosinseln (Keelinginseln)'), ('CO', 'Kolumbien'), ('KM', 'Komoren'), ('CG', 'Kongo'), ('CD', 'Kongo (Demokratische Republik)'), ('HR', 'Kroatien'), ('CU', 'Kuba'), ('KW', 'Kuwait'), ('LA', 'Laos'), ('LS', 'Lesotho'), ('LV', 'Lettland'), ('LB', 'Libanon'), ('LR', 'Liberia'), ('LY', 'Libyen'), ('LI', 'Liechtenstein'), ('LT', 'Litauen'), ('LU', 'Luxemburg'), ('MO', 'Macao'), ('MG', 'Madagaskar'), ('MW', 'Malawi'), ('MY', 'Malaysia'), ('MV', 'Malediven'), ('ML', 'Mali'), ('MT', 'Malta'), ('MA', 'Marokko'), ('MH', 'Marshallinseln'), ('MQ', 'Martinique'), ('MR', 'Mauretanien'), ('MU', 'Mauritius'), ('YT', 'Mayotte'), ('MK', 'Mazedonien'), ('MX', 'Mexiko'), ('FM', 'Mikronesien (Föderierte Staaten von)'), ('MD', 'Moldawien'), ('MC', 'Monaco'), ('MN', 'Mongolei'), ('ME', 'Montenegro'), ('MS', 'Montserrat'), ('MZ', 'Mozambique'), ('MM', 'Myanmar'), ('NA', 'Namibia'), ('NR', 'Nauru'), ('NP', 'Nepal'), ('NC', 'Neukaledonien'), ('NZ', 'Neuseeland'), ('NI', 'Nicaragua'), ('NL', 'Niederlande'), ('NE', 'Niger'), ('NG', 'Nigeria'), ('NU', 'Niue'), ('KP', 'Nordkorea'), ('NF', 'Norfolkinsel'), ('NO', 'Norwegen'), ('OM', 'Oman'), ('AT', 'Österreich'), ('TL', 'Osttimor'), ('PK', 'Pakistan'), ('PS', 'Palästina'), ('PW', 'Palau'), ('PA', 'Panama'), ('PG', 'Papua Neu Guinea'), ('PY', 'Paraguay'), ('PE', 'Peru'), ('PH', 'Philippinen'), ('PN', 'Pitcairn'), ('PL', 'Polen'), ('PT', 'Portugal'), ('PR', 'Puerto Rico'), ('RE', 'Réunion'), ('RW', 'Ruanda'), ('RO', 'Rumänien'), ('RU', 'Russland'), ('BL', 'Saint-Barthélemy'), ('PM', 'Saint-Pierre und Miquelon'), ('SB', 'Salomonen'), ('ZM', 'Sambia'), ('WS', 'Samoa'), ('SM', 'San Marino'), ('ST', 'São Tomé und Príncipe'), ('SA', 'Saudi Arabien'), ('SE', 'Schweden'), ('CH', 'Schweiz'), ('SN', 'Senegal'), ('RS', 'Serbien'), ('SC', 'Seychellen'), ('SL', 'Sierra Leone'), ('ZW', 'Simbabwe'), ('SG', 'Singapur'), ('SX', 'Sint Maarten (niederländischer Teil)'), ('SK', 'Slowakei'), ('SI', 'Slowenien'), ('SO', 'Somalia'), ('ES', 'Spanien'), ('SJ', 'Spitzbergen und Jan Mayen'), ('LK', 'Sri Lanka'), ('SH', 'St. Helena, Ascension und Tristan da Cunha'), ('KN', 'St. Kitts und Nevis'), ('LC', 'St. Lucia'), ('MF', 'St. Martin (französischer Teil)'), ('VC', 'St. Vincent und die Grenadinen'), ('ZA', 'Südafrika'), ('SD', 'Sudan'), ('GS', 'Südgeorgien und die Südlichen Sandwichinseln'), ('KR', 'Südkorea'), ('SS', 'Südsudan'), ('SR', 'Surinam'), ('SZ', 'Swasiland'), ('SY', 'Syrien'), ('TJ', 'Tadschikistan'), ('TW', 'Taiwan'), ('TZ', 'Tansania'), ('TH', 'Thailand'), ('TG', 'Togo'), ('TK', 'Tokelau'), ('TO', 'Tonga'), ('TT', 'Trinidad und Tobago'), ('TD', 'Tschad'), ('CZ', 'Tschechien'), ('TN', 'Tunesien'), ('TR', 'Türkei'), ('TM', 'Turkmenistan'), ('TC', 'Turks- und Caicosinseln'), ('TV', 'Tuvalu'), ('UM', 'USA - Sonstige Kleine Inseln'), ('UG', 'Uganda'), ('UA', 'Ukraine'), ('HU', 'Ungarn'), ('UY', 'Uruguay'), ('UZ', 'Usbekistan'), ('VU', 'Vanuatu'), ('VA', 'Vatikanstadt'), ('VE', 'Venezuela'), ('AE', 'Vereinigte Arabische Emirate'), ('US', 'Vereinigte Staaten von Amerika'), ('GB', 'Vereinigtes Königreich'), ('VN', 'Vietnam'), ('WF', 'Wallis und Futuna'), ('CX', 'Weihnachtsinsel'), ('BY', 'Weißrussland'), ('EH', 'Westsahara'), ('CF', 'Zentralafrikanische Republik'), ('CY', 'Zypern')], default='', max_length=2, verbose_name='country code'),
        ),
    ]
