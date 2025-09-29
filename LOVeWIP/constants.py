"""
Sovelluksen vakiot ja konfiguraatiot
"""

DISTRACTORS = [
    {
        "scenario": "Potilaan omainen tulee kysymään, voisitko tuoda hänen läheiselleen lasin vettä.",
        "options": ["Lupaan tuoda veden heti lääkkeenjaon jälkeen.", "Keskeytän ja haen veden välittömästi."],
        "correct": 0
    },
    {
        "scenario": "Lääkäri soittaa ja kysyy toisen potilaan vointia.",
        "options": ["Pyydän lääkäriä soittamaan hetken päästä uudelleen.", "Vastaan lääkärin kysymyksiin lääkkeenjaon ohessa."],
        "correct": 0
    },
    {
        "scenario": "Viereisen sängyn potilas valittaa äkillistä, kovaa rintakipua.",
        "options": ["Soitan hoitokelloa ja pyydän kollegan apuun.", "Jätän lääkkeet ja menen välittömästi potilaan luo."],
        "correct": 1
    },
    {
        "scenario": "Lääkehuoneen hälytys alkaa soida.",
        "options": ["Tarkistan tilanteen nopeasti.", "Jatkan lääkkeenjakoa, joku muu varmasti hoitaa."],
        "correct": 0
    },
    {
        "scenario": "Levoton potilas yrittää nousta sängystä, vaikka hänellä on kaatumisriski.",
        "options": ["Puhun potilaalle rauhallisesti ja ohjaan takaisin sänkyyn.", "Huudan apua käytävältä."],
        "correct": 0
    },
    {
        "scenario": "Asiakas pyytää apua WC:hen juuri kun olet jakamassa lääkkeitä toiselle asiakkaalle.",
        "options": ["Pyydän asiakasta odottamaan hetken.", "Keskeytän lääkkeenjaon ja autan WC:hen."],
        "correct": 0
    },
    {
        "scenario": "Kollega tulee kysymään kiireesti: 'Muistatko missä säilytämme insuliinikyniä?'",
        "options": ["Vastaan nopeasti 'Jääkaapissa' ja jatkan.", "Lopetan ja näytän tarkasti missä ne ovat."],
        "correct": 0
    },
    {
        "scenario": "Asiakkaan omainen soittaa ja kysyy: 'Onko äitini ottanut aamulääkkeensä?'",
        "options": ["Pyydän soittamaan puoli tuntia myöhemmin.", "Tarkistan heti kirjauksista ja kerron."],
        "correct": 0
    },
    {
        "scenario": "Huomaat lattialla vesilätäkän käytävässä heti oven vieressä.",
        "options": ["Merkitsen muistiin ja ilmoitan siivoushenkilökunnalle.", "Haen heti moppauksen ja korjaan tilanteen."],
        "correct": 0
    },
    {
        "scenario": "Asiakas alkaa itkemään ja sanoo: 'Minua pelottaa, enkä halua ottaa lääkkeitä.'",
        "options": ["Rauhoittelen ja selitän lääkkeiden tärkeyden.", "Jätän lääkkeet ottamatta ja keskustelen ensin."],
        "correct": 1
    },
    {
        "scenario": "Palovaroitin alkaa piipata keittiöstä (mahdollisesti väärästi).",
        "options": ["Tarkistan tilanteen nopeasti keittiöstä.", "Soitan hätäkeskukseen varmuuden vuoksi."],
        "correct": 0
    },
    {
        "scenario": "Asiakkaiden välille syntyy kiista yhteisessä tilassa.",
        "options": ["Menen rauhoittamaan tilannetta.", "Pyydän kollegan hoitamaan asian."],
        "correct": 0
    },
    {
        "scenario": "Huomaat että toisen asiakkaan verensokeri näyttää olevan huolestuttavan alhainen.",
        "options": ["Keskeytän ja mittaan verensokerin heti.", "Merkitsen muistiin ja tarkistan mittauksen jälkeen."],
        "correct": 0
    },
    {
        "scenario": "Asiakkaan avustaja tulee kysymään: 'Missä vaiheessa lääkkeenjakoa mennään?'",
        "options": ["Kerron nopeasti tilanteen ja jatkan.", "Näytän tarkasti mistä mennään ja mitä on jäljellä."],
        "correct": 0
    },
    {
        "scenario": "Kuulet keittiöstä kovaa kolinaa ja asiakkaan huudahduksen.",
        "options": ["Huudan 'Kaikko kunnossa?' ja kuuntelen vastausta.", "Juoksen heti katsomaan mitä tapahtui."],
        "correct": 1
    },
    {
        "scenario": "Asiakas kysyy: 'Voinko ottaa kaksi särky lääkettä kerralla kun pää särkee niin kovaa?'",
        "options": ["Selitän miksi annostusta ei saa muuttaa.", "Soitan lääkärille kysyäkseni lisäannoksesta."],
        "correct": 0
    },
    {
        "scenario": "Huomaat että asiakkaalla on ihottumaa käsivarressa lääkelaastarien kohdalla.",
        "options": ["Merkitsen havainnon ja jatkan lääkkeenjakoa.", "Tutkin ihon kunnon tarkemmin heti."],
        "correct": 1
    },
    {
        "scenario": "Toimintakeskuksen johtaja tulee kysymään: 'Onko Virtasella ollut oksentelua tänään?'",
        "options": ["Vastaan sen mitä tiedän ja jatkan.", "Lopetan ja tarkistan kirjaukset huolellisesti."],
        "correct": 0
    },
    {
        "scenario": "Asiakas pudottaa lasillisen vettä lattialle ja se särkyi.",
        "options": ["Pyydän asiakasta siirtymään turvallisesti ja siivotan lasit.", "Huudan apua ja pyydän asiakasta pysymään paikallaan."],
        "correct": 0
    },
    {
        "scenario": "Kollega tulee sanomaan: 'Unohdin mainita että Marja tarvitsee antibioottinsa tunnin päästä.'",
        "options": ["Merkitsen muistiini ja huolehdin asiasta.", "Lopetan nykyisen ja hoidan Marjan lääkkeen heti."],
        "correct": 0
    }
]